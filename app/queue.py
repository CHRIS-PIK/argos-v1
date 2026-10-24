from __future__ import annotations

import hashlib
import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

import redis

from app.observability.metrics import (
    QUEUE_BACKLOG,
    QUEUE_MESSAGES,
    QUEUE_OLDEST_PENDING_AGE,
)

STREAM = os.getenv("QUEUE_STREAM", "argos:events")
GROUP = os.getenv("QUEUE_GROUP", "argos-workers")
DEAD_STREAM = f"{STREAM}:dead"
DEDUP_PREFIX = f"{STREAM}:dedup:"
DEDUP_TTL_SECONDS = int(os.getenv("QUEUE_DEDUP_TTL_SECONDS", str(7 * 24 * 3600)))

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
        )
    return _client


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def consumer_name() -> str:
    return os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"


def ensure_group() -> None:
    try:
        get_redis().xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def _decode(message_id: str, fields: dict[str, str]) -> dict[str, Any]:
    return {
        "id": message_id,
        "tenant_id": fields["tenant_id"],
        "source": fields["source"],
        "collector_name": fields["event_type"],
        "schema_version": fields["schema_version"],
        "batch_id": fields.get("batch_id") or None,
        "page_number": int(fields["page"]),
        "collected_at": datetime.fromisoformat(fields["collected_at"]),
        "bucket_at": datetime.fromisoformat(fields["bucket_at"]),
        "payload": fields["payload"],
    }


def enqueue_event(
    tenant_id: str,
    source: str,
    event_type: str,
    schema_version: str,
    batch_id: str | None,
    page_number: int,
    collected_at: datetime,
    bucket_at: datetime,
    items: list[dict[str, Any]],
) -> bool:
    """Persiste um lote validado. Retorna False quando o lote já havia sido enfileirado."""
    payload_text = json.dumps(items, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload_sha = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    if batch_id:
        dedup_source = f"{tenant_id}|{source}|{event_type}|{batch_id}|{page_number}"
    else:
        dedup_source = (
            f"{tenant_id}|{source}|{event_type}|{bucket_at.isoformat()}|"
            f"{page_number}|{payload_sha}"
        )
    dedup_key = DEDUP_PREFIX + hashlib.sha256(dedup_source.encode("utf-8")).hexdigest()

    client = get_redis()
    if not client.set(dedup_key, "1", nx=True, ex=DEDUP_TTL_SECONDS):
        return False
    try:
        client.xadd(STREAM, {
            "tenant_id": tenant_id,
            "source": source,
            "event_type": event_type,
            "schema_version": schema_version,
            "batch_id": batch_id or "",
            "page": str(page_number),
            "collected_at": collected_at.isoformat(),
            "bucket_at": bucket_at.isoformat(),
            "payload": payload_text,
        })
    except Exception:
        # Sem isso um reenvio seria tratado como duplicado e o lote se perderia.
        client.delete(dedup_key)
        raise
    return True


def read_new(count: int, block_ms: int) -> list[dict[str, Any]]:
    result = get_redis().xreadgroup(
        GROUP, consumer_name(), {STREAM: ">"}, count=count, block=block_ms
    )
    messages = []
    for _stream, entries in result or []:
        for message_id, fields in entries:
            message = _decode(message_id, fields)
            message["attempts"] = 1
            messages.append(message)
    return messages


def claim_stale(min_idle_ms: int, count: int) -> list[dict[str, Any]]:
    """Retoma mensagens entregues e não confirmadas (falha ou worker morto)."""
    client = get_redis()
    _next, entries, _deleted = client.xautoclaim(
        STREAM, GROUP, consumer_name(), min_idle_time=min_idle_ms, start_id="0-0", count=count
    )
    messages = []
    for message_id, fields in entries:
        if not fields:
            # Entrada já removida do stream; apenas limpa o pendente.
            client.xack(STREAM, GROUP, message_id)
            continue
        pending = client.xpending_range(STREAM, GROUP, min=message_id, max=message_id, count=1)
        message = _decode(message_id, fields)
        message["attempts"] = int(pending[0]["times_delivered"]) if pending else 1
        messages.append(message)
    return messages


def ack(message_id: str) -> None:
    client = get_redis()
    pipe = client.pipeline()
    pipe.xack(STREAM, GROUP, message_id)
    pipe.xdel(STREAM, message_id)
    pipe.execute()


def dead_letter(message: dict[str, Any], error: str) -> None:
    client = get_redis()
    original = client.xrange(STREAM, message["id"], message["id"])
    fields = original[0][1] if original else {}
    fields = {**fields, "error": error[-8000:], "original_id": message["id"],
              "attempts": str(message["attempts"])}
    pipe = client.pipeline()
    pipe.xadd(DEAD_STREAM, fields)
    pipe.xack(STREAM, GROUP, message["id"])
    pipe.xdel(STREAM, message["id"])
    pipe.execute()


def should_give_up(attempts: int) -> bool:
    return attempts >= int(os.getenv("QUEUE_MAX_ATTEMPTS", "5"))


def update_queue_metrics() -> None:
    client = get_redis()
    lag = 0
    pending = 0
    for group in client.xinfo_groups(STREAM):
        if group["name"] == GROUP:
            lag = int(group.get("lag") or 0)
            pending = int(group.get("pending") or 0)
    dead = int(client.xlen(DEAD_STREAM))

    QUEUE_MESSAGES.labels(status="PENDING").set(lag)
    QUEUE_MESSAGES.labels(status="PROCESSING").set(pending)
    QUEUE_MESSAGES.labels(status="DEAD").set(dead)
    QUEUE_BACKLOG.set(lag + pending)

    age_seconds = 0.0
    oldest = client.xrange(STREAM, count=1)
    if oldest:
        created_ms = int(oldest[0][0].split("-")[0])
        age_seconds = max(0.0, datetime.now(timezone.utc).timestamp() - created_ms / 1000)
    QUEUE_OLDEST_PENDING_AGE.set(age_seconds)
