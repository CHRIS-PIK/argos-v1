from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.ingest.keys import CollectorIdentity
from app.query.filters import Filters

DEFAULT_WINDOW = timedelta(hours=24)

ENTITY_COLUMNS = (
    "tenant_id, event_type, source, schema_version, entity_id, name, status, dimensions, "
    "collected_at, ingested_at, batch_id"
)
EVENT_COLUMNS = (
    "tenant_id, event_type, source, schema_version, entity_id, bucket_at, name, status, "
    "dimensions, collected_at, ingested_at, batch_id"
)


def entities_query(
    filters: Filters,
    identity: CollectorIdentity,
    limit: int,
    cursor: list[Any] | None = None,
    include_payload: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Entidades em ordem estável; `cursor` é [event_type, source, entity_id] da última linha."""
    clauses, params = filters.where(identity)
    if cursor:
        clauses.append("(event_type, source, entity_id) > ({c0:String}, {c1:String}, {c2:String})")
        params.update(c0=str(cursor[0]), c1=str(cursor[1]), c2=str(cursor[2]))
    columns = ENTITY_COLUMNS + (", payload" if include_payload else "")
    params["limit"] = limit
    sql = (
        f"SELECT {columns} FROM entity_latest FINAL WHERE {' AND '.join(clauses)} "
        "ORDER BY event_type, source, entity_id LIMIT {limit:UInt32}"
    )
    return sql, params


def resolve_window(
    time_from: datetime | None, time_to: datetime | None
) -> tuple[datetime, datetime]:
    time_to = time_to or datetime.now(timezone.utc)
    time_from = time_from or (time_to - DEFAULT_WINDOW)
    if time_from.tzinfo is None:
        time_from = time_from.replace(tzinfo=timezone.utc)
    if time_to.tzinfo is None:
        time_to = time_to.replace(tzinfo=timezone.utc)
    if time_from >= time_to:
        raise HTTPException(status_code=422, detail="'from' must be before 'to'")
    return time_from, time_to


def events_query(
    filters: Filters,
    identity: CollectorIdentity,
    time_from: datetime,
    time_to: datetime,
    limit: int,
    cursor: list[Any] | None = None,
    include_payload: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Eventos do mais novo para o mais antigo; `cursor` é [epoch, event_type, source, entity_id]."""
    clauses, params = filters.where(identity)
    clauses.append("bucket_at >= {t_from:DateTime('UTC')} AND bucket_at <= {t_to:DateTime('UTC')}")
    params.update(t_from=time_from, t_to=time_to)
    if cursor:
        clauses.append(
            "(bucket_at, event_type, source, entity_id) < "
            "(toDateTime({c0:UInt32}, 'UTC'), {c1:String}, {c2:String}, {c3:String})"
        )
        params.update(c0=int(cursor[0]), c1=str(cursor[1]), c2=str(cursor[2]), c3=str(cursor[3]))
    columns = EVENT_COLUMNS + (", payload" if include_payload else "")
    params["limit"] = limit
    sql = (
        f"SELECT {columns} FROM events FINAL WHERE {' AND '.join(clauses)} "
        "ORDER BY bucket_at DESC, event_type DESC, source DESC, entity_id DESC "
        "LIMIT {limit:UInt32}"
    )
    return sql, params


def entity_cursor(row: dict[str, Any]) -> list[Any]:
    return [row["event_type"], row["source"], row["entity_id"]]


def event_cursor(row: dict[str, Any]) -> list[Any]:
    bucket = row["bucket_at"]
    if bucket.tzinfo is None:
        bucket = bucket.replace(tzinfo=timezone.utc)
    return [int(bucket.timestamp()), row["event_type"], row["source"], row["entity_id"]]


def count_query(
    dataset: str,
    filters: Filters,
    identity: CollectorIdentity,
    window: tuple[datetime, datetime] | None = None,
) -> tuple[str, dict[str, Any]]:
    clauses, params = filters.where(identity)
    if dataset == "events":
        time_from, time_to = window
        clauses.append("bucket_at >= {t_from:DateTime('UTC')} AND bucket_at <= {t_to:DateTime('UTC')}")
        params.update(t_from=time_from, t_to=time_to)
        table = "events"
    else:
        table = "entity_latest"
    return f"SELECT count() AS total FROM {table} FINAL WHERE {' AND '.join(clauses)}", params
