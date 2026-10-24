from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.ingest.contract import SchemaRegistry, default_registry
from app.ingest.keys import CollectorIdentity, KeyStore
from app.observability.runtime import configure_observability
from app.query import db
from app.query.filters import (
    Filters,
    decode_cursor,
    dimensions_from_query,
    encode_cursor,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

configure_observability("query")

MAX_PAGE = 1000
DEFAULT_WINDOW = timedelta(hours=24)

app = FastAPI(title="Argos Query API", version="1")
keystore = KeyStore()
registry: SchemaRegistry = default_registry()


def require_reader(x_api_key: str | None = Header(default=None)) -> CollectorIdentity:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    identity = keystore.authenticate(x_api_key)
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    if not identity.has_role("reader"):
        raise HTTPException(status_code=403, detail="API key role cannot read data")
    return identity


def require_admin(x_api_key: str | None = Header(default=None)) -> CollectorIdentity:
    identity = require_reader(x_api_key)
    if not identity.has_role("admin"):
        raise HTTPException(status_code=403, detail="admin role required")
    return identity


def iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def serialize(row: dict[str, Any], include_payload: bool) -> dict[str, Any]:
    out = {key: iso(value) for key, value in row.items() if key != "payload"}
    if include_payload and "payload" in row:
        try:
            out["payload"] = json.loads(row["payload"])
        except (TypeError, ValueError):
            out["payload"] = row["payload"]
    return out


def common_filters(
    request: Request,
    event_type: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, max_length=64),
    status: str | None = Query(default=None, max_length=128),
    q: str | None = Query(default=None, max_length=128, description="Busca em nome e id"),
) -> Filters:
    return Filters(
        event_type=event_type,
        source=source,
        status=status,
        q=q,
        dimensions=dimensions_from_query(request.query_params),
    )


ENTITY_COLUMNS = (
    "tenant_id, event_type, source, schema_version, entity_id, name, status, dimensions, "
    "collected_at, ingested_at, batch_id"
)
EVENT_COLUMNS = (
    "tenant_id, event_type, source, schema_version, entity_id, bucket_at, name, status, "
    "dimensions, collected_at, ingested_at, batch_id"
)


def _page(rows: list[dict[str, Any]], limit: int, cursor_of) -> tuple[list[dict[str, Any]], str | None]:
    if len(rows) > limit:
        rows = rows[:limit]
        return rows, encode_cursor(cursor_of(rows[-1]))
    return rows, None


@app.get("/v1/entities")
def list_entities(
    filters: Filters = Depends(common_filters),
    identity: CollectorIdentity = Depends(require_reader),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE),
    cursor: str | None = None,
    include_payload: bool = False,
):
    clauses, params = filters.where(identity)
    if cursor:
        last = decode_cursor(cursor, 3)
        clauses.append("(event_type, source, entity_id) > ({c0:String}, {c1:String}, {c2:String})")
        params.update(c0=str(last[0]), c1=str(last[1]), c2=str(last[2]))
    columns = ENTITY_COLUMNS + (", payload" if include_payload else "")
    params["limit"] = limit + 1
    sql = (
        f"SELECT {columns} FROM entity_latest FINAL WHERE {' AND '.join(clauses)} "
        "ORDER BY event_type, source, entity_id LIMIT {limit:UInt32}"
    )
    page, next_cursor = _page(
        db.rows(sql, params), limit, lambda r: [r["event_type"], r["source"], r["entity_id"]]
    )
    return {
        "items": [serialize(row, include_payload) for row in page],
        "next_cursor": next_cursor,
    }


@app.get("/v1/entities/count")
def count_entities(
    filters: Filters = Depends(common_filters),
    identity: CollectorIdentity = Depends(require_reader),
):
    clauses, params = filters.where(identity)
    sql = f"SELECT count() AS total FROM entity_latest FINAL WHERE {' AND '.join(clauses)}"
    return {"total": int(db.rows(sql, params)[0]["total"])}


@app.get("/v1/entity")
def get_entity(
    event_type: str = Query(max_length=64),
    source: str = Query(max_length=64),
    entity_id: str = Query(max_length=512),
    history: int = Query(default=50, ge=0, le=500),
    identity: CollectorIdentity = Depends(require_reader),
):
    """Detalhe de uma entidade: último estado com payload e histórico recente."""
    filters = Filters(event_type=event_type, source=source, entity_id=entity_id)
    clauses, params = filters.where(identity)
    where = " AND ".join(clauses)
    current = db.rows(
        f"SELECT {ENTITY_COLUMNS}, payload FROM entity_latest FINAL WHERE {where} LIMIT 1", params
    )
    if not current:
        raise HTTPException(status_code=404, detail="entity not found")
    recent: list[dict[str, Any]] = []
    if history:
        recent = db.rows(
            f"SELECT {EVENT_COLUMNS}, payload FROM events FINAL WHERE {where} "
            "ORDER BY bucket_at DESC LIMIT {history:UInt32}",
            {**params, "history": history},
        )
    return {
        "entity": serialize(current[0], True),
        "history": [serialize(row, True) for row in recent],
    }


@app.get("/v1/events")
def list_events(
    request: Request,
    filters: Filters = Depends(common_filters),
    identity: CollectorIdentity = Depends(require_reader),
    entity_id: str | None = Query(default=None, max_length=512),
    time_from: datetime | None = Query(default=None, alias="from"),
    time_to: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE),
    cursor: str | None = None,
    include_payload: bool = False,
):
    filters.entity_id = entity_id
    clauses, params = filters.where(identity)

    now = datetime.now(timezone.utc)
    time_to = time_to or now
    time_from = time_from or (time_to - DEFAULT_WINDOW)
    if time_from.tzinfo is None:
        time_from = time_from.replace(tzinfo=timezone.utc)
    if time_to.tzinfo is None:
        time_to = time_to.replace(tzinfo=timezone.utc)
    if time_from >= time_to:
        raise HTTPException(status_code=422, detail="'from' must be before 'to'")
    clauses.append("bucket_at >= {t_from:DateTime('UTC')} AND bucket_at <= {t_to:DateTime('UTC')}")
    params.update(t_from=time_from, t_to=time_to)

    if cursor:
        last = decode_cursor(cursor, 4)
        clauses.append(
            "(bucket_at, event_type, source, entity_id) < "
            "(toDateTime({c0:UInt32}, 'UTC'), {c1:String}, {c2:String}, {c3:String})"
        )
        params.update(c0=int(last[0]), c1=str(last[1]), c2=str(last[2]), c3=str(last[3]))

    columns = EVENT_COLUMNS + (", payload" if include_payload else "")
    params["limit"] = limit + 1
    sql = (
        f"SELECT {columns} FROM events FINAL WHERE {' AND '.join(clauses)} "
        "ORDER BY bucket_at DESC, event_type DESC, source DESC, entity_id DESC "
        "LIMIT {limit:UInt32}"
    )

    def cursor_of(row: dict[str, Any]) -> list[Any]:
        bucket = row["bucket_at"]
        if bucket.tzinfo is None:
            bucket = bucket.replace(tzinfo=timezone.utc)
        return [int(bucket.timestamp()), row["event_type"], row["source"], row["entity_id"]]

    page, next_cursor = _page(db.rows(sql, params), limit, cursor_of)
    return {
        "items": [serialize(row, include_payload) for row in page],
        "next_cursor": next_cursor,
    }


@app.get("/v1/meta")
def meta(identity: CollectorIdentity = Depends(require_reader)):
    """Catálogo para o front montar filtros sem conhecer nenhuma fonte."""
    clauses, params = Filters().where(identity)
    where = " AND ".join(clauses)

    sources = db.rows(
        "SELECT event_type, source, count() AS entities, max(ingested_at) AS last_ingested "
        f"FROM entity_latest FINAL WHERE {where} GROUP BY event_type, source "
        "ORDER BY event_type, source",
        params,
    )
    statuses = db.rows(
        "SELECT event_type, groupUniqArray(50)(status) AS statuses "
        f"FROM entity_latest FINAL WHERE {where} GROUP BY event_type",
        params,
    )
    dimensions = db.rows(
        "SELECT event_type, k AS key, uniqExact(dimensions[k]) AS distinct_values "
        f"FROM entity_latest FINAL ARRAY JOIN mapKeys(dimensions) AS k WHERE {where} "
        "GROUP BY event_type, k ORDER BY event_type, k",
        params,
    )

    types: dict[str, dict[str, Any]] = {}
    for row in sources:
        entry = types.setdefault(
            row["event_type"],
            {"event_type": row["event_type"], "entities": 0, "sources": [],
             "statuses": [], "dimensions": []},
        )
        entry["entities"] += int(row["entities"])
        entry["sources"].append({
            "source": row["source"],
            "entities": int(row["entities"]),
            "last_ingested": iso(row["last_ingested"]),
        })
    for row in statuses:
        if row["event_type"] in types:
            types[row["event_type"]]["statuses"] = sorted(s for s in row["statuses"] if s)
    for row in dimensions:
        if row["event_type"] in types:
            types[row["event_type"]]["dimensions"].append(
                {"key": row["key"], "distinct_values": int(row["distinct_values"])}
            )

    schemas = [
        entry for entry in registry.catalog()
        if identity.can_send(entry["event_type"]) or "*" in identity.allowed_event_types
    ]
    return {"tenant_id": identity.tenant_id, "types": list(types.values()), "schemas": schemas}


@app.get("/v1/dimensions/values")
def dimension_values(
    event_type: str = Query(max_length=64),
    key: str = Query(max_length=64),
    q: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    identity: CollectorIdentity = Depends(require_reader),
):
    """Valores de uma dimensão, para preencher filtros."""
    clauses, params = Filters(event_type=event_type).where(identity)
    clauses.append("mapContains(dimensions, {key:String})")
    params["key"] = key
    if q:
        clauses.append("positionCaseInsensitive(dimensions[{key:String}], {q:String}) > 0")
        params["q"] = q
    params["limit"] = limit
    rows = db.rows(
        "SELECT dimensions[{key:String}] AS value, count() AS entities "
        f"FROM entity_latest FINAL WHERE {' AND '.join(clauses)} "
        "GROUP BY value ORDER BY entities DESC, value LIMIT {limit:UInt32}",
        params,
    )
    return {"values": [{"value": r["value"], "entities": int(r["entities"])} for r in rows]}


@app.get("/v1/queue")
def queue_status(_: CollectorIdentity = Depends(require_admin)):
    from app.queue import queue_stats

    return queue_stats()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
