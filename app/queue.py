from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import connection


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def enqueue_page(
    collector_name: str,
    endpoint: str,
    page_number: int,
    collected_at: datetime,
    bucket_at: datetime,
    items: list[dict[str, Any]],
) -> bool:
    payload_text = json.dumps(items, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload_sha = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    dedup_source = f"{collector_name}|{endpoint}|{bucket_at.isoformat()}|{page_number}|{payload_sha}"
    dedup_key = hashlib.sha256(dedup_source.encode("utf-8")).hexdigest()

    sql = """
    INSERT IGNORE INTO ingestion_queue
    (collector_name, endpoint, page_number, collected_at, bucket_at, payload,
     payload_sha256, dedup_key, status, available_at)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)
    """
    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute(sql, (
            collector_name, endpoint, page_number, collected_at, bucket_at,
            payload_text, payload_sha, dedup_key, collected_at
        ))
        return cur.rowcount == 1


def recover_stale_messages(lock_timeout_seconds: int) -> int:
    cutoff = utc_now() - timedelta(seconds=lock_timeout_seconds)
    sql = """
    UPDATE ingestion_queue
       SET status='PENDING', locked_at=NULL, locked_by=NULL,
           available_at=%s,
           error_message=CONCAT(COALESCE(error_message,''), '\nRecovered stale lock')
     WHERE status='PROCESSING' AND locked_at < %s
    """
    now = utc_now()
    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute(sql, (now, cutoff))
        return cur.rowcount


def claim_message() -> dict[str, Any] | None:
    worker_id = os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    now = utc_now()
    with connection() as cnx:
        cur = cnx.cursor(dictionary=True)
        cur.execute("""
            SELECT id, collector_name, endpoint, page_number, collected_at,
                   bucket_at, payload, attempts
              FROM ingestion_queue
             WHERE status IN ('PENDING','FAILED')
               AND available_at <= %s
             ORDER BY id
             LIMIT 1
             FOR UPDATE SKIP LOCKED
        """, (now,))
        row = cur.fetchone()
        if not row:
            return None

        cur.execute("""
            UPDATE ingestion_queue
               SET status='PROCESSING', attempts=attempts+1,
                   locked_at=%s, locked_by=%s, error_message=NULL
             WHERE id=%s
        """, (now, worker_id, row["id"]))
        row["attempts"] = int(row["attempts"]) + 1
        return row


def mark_processed(message_id: int) -> None:
    now = utc_now()
    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute("""
            UPDATE ingestion_queue
               SET status='PROCESSED', processed_at=%s,
                   locked_at=NULL, locked_by=NULL, error_message=NULL
             WHERE id=%s
        """, (now, message_id))


def mark_failed(message_id: int, attempts: int, error: str) -> None:
    max_attempts = int(os.getenv("QUEUE_MAX_ATTEMPTS", "5"))
    base_delay = int(os.getenv("QUEUE_RETRY_BASE_SECONDS", "30"))
    capped_error = error[-8000:]
    now = utc_now()

    if attempts >= max_attempts:
        status = "DEAD"
        available_at = now
    else:
        status = "FAILED"
        delay = min(3600, base_delay * (2 ** max(0, attempts - 1)))
        available_at = now + timedelta(seconds=delay)

    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute("""
            UPDATE ingestion_queue
               SET status=%s, available_at=%s, error_message=%s,
                   locked_at=NULL, locked_by=NULL
             WHERE id=%s
        """, (status, available_at, capped_error, message_id))
