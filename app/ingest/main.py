from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.ingest.contract import EventBatch, SchemaRegistry, default_registry
from app.ingest.keys import CollectorIdentity, KeyStore
from app.observability.metrics import (
    INGEST_ITEMS,
    INGEST_REQUEST_DURATION,
    INGEST_REQUESTS,
)
from app.observability.runtime import configure_observability
from app.queue import enqueue_event

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

configure_observability("ingest")

MAX_ITEMS_PER_BATCH = max(1, int(os.getenv("INGEST_MAX_ITEMS", "5000")))
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_PAST_AGE = timedelta(hours=int(os.getenv("INGEST_MAX_PAST_HOURS", "24")))

app = FastAPI(title="Argos Ingest API", version="1")
registry: SchemaRegistry = default_registry()
keystore = KeyStore()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 10) * 10, second=0, microsecond=0)


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def require_collector(x_api_key: str | None = Header(default=None)) -> CollectorIdentity:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    identity = keystore.authenticate(x_api_key)
    if identity is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    return identity


def reject(event_type: str, result: str, status: int, detail: object) -> JSONResponse:
    INGEST_REQUESTS.labels(event_type=event_type, result=result).inc()
    return JSONResponse(status_code=status, content={"status": "rejected", "detail": detail})


@app.post("/v1/events", status_code=202)
def post_events(
    batch: EventBatch,
    identity: CollectorIdentity = Depends(require_collector),
):
    started = time.monotonic()
    event_type = batch.event_type

    if not identity.can_send(event_type):
        return reject(event_type, "forbidden", 403, "API key not allowed for this event_type")

    if len(batch.items) > MAX_ITEMS_PER_BATCH:
        return reject(
            event_type, "too_large", 413, f"max {MAX_ITEMS_PER_BATCH} items per batch"
        )

    if not registry.has(event_type, batch.schema_version):
        return reject(
            event_type,
            "unknown_schema",
            422,
            f"no schema registered for event_type={event_type} version={batch.schema_version}",
        )

    errors = registry.validate(event_type, batch.schema_version, batch.items)
    if errors:
        return reject(event_type, "invalid", 422, errors)

    now = utc_now()
    collected_at = to_naive_utc(batch.collected_at) if batch.collected_at else now
    if collected_at > now + MAX_FUTURE_SKEW:
        return reject(event_type, "invalid", 422, "collected_at is in the future")
    if collected_at < now - MAX_PAST_AGE:
        return reject(event_type, "invalid", 422, "collected_at is too old")

    is_new = enqueue_event(
        tenant_id=identity.tenant_id,
        source=batch.source,
        event_type=event_type,
        schema_version=batch.schema_version,
        batch_id=batch.batch_id,
        page_number=batch.page,
        collected_at=collected_at,
        bucket_at=bucket_10m(collected_at),
        items=batch.items,
    )

    result = "accepted" if is_new else "duplicate"
    INGEST_REQUESTS.labels(event_type=event_type, result=result).inc()
    if is_new:
        INGEST_ITEMS.labels(event_type=event_type).inc(len(batch.items))
    INGEST_REQUEST_DURATION.labels(event_type=event_type).observe(time.monotonic() - started)
    return {"status": "accepted", "duplicate": not is_new, "items": len(batch.items)}


@app.get("/v1/schemas")
def list_schemas(_: CollectorIdentity = Depends(require_collector)):
    return {"schemas": registry.catalog()}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
