from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import start_http_server

from aruba_client import ArubaClient
from config import settings
from metrics import (
    COLLECTOR_BATCHES_SENT,
    COLLECTOR_COLLECTION_DURATION,
    COLLECTOR_CYCLES,
    COLLECTOR_LAST_SUCCESS,
    COLLECTOR_PAGES_COLLECTED,
    COLLECTOR_PAGINATION_STOPS,
)
from runtime import configure_observability
from sender import IngestClient, IngestRejected


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

configure_observability("collector-aruba")
tracer = trace.get_tracer("argos.collector.aruba")

# event_type -> endpoint da Aruba. Licensing e AI Insights continuam desligados
# até o cliente pedir e o endpoint ser validado para o tenant.
STATIC_ENDPOINTS = {
    "aps": "network-monitoring/v1/aps",
    "clients": "network-monitoring/v1/clients",
    "switches": "network-monitoring/v1/switches",
    "radios": "network-monitoring/v1/radios",
    "alerts": "network-notifications/v1/alerts",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 10) * 10, second=0, microsecond=0)


def payload_sha256(items: list) -> str:
    canonical = json.dumps(
        items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def batch_id_for(event_type: str, bucket_at: datetime, page: int, page_hash: str) -> str:
    # Determinístico: reenviar a mesma página do mesmo bucket é idempotente.
    raw = f"{settings.source}|{event_type}|{bucket_at.isoformat()}|{page}|{page_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def collect_endpoint(event_type: str, endpoint: str, ingest: IngestClient) -> tuple[int, int]:
    with tracer.start_as_current_span(
        "argos.collect_endpoint",
        attributes={"argos.event_type": event_type, "http.route": endpoint},
    ) as span:
        client = ArubaClient()
        collected_at = utc_now()
        bucket_at = bucket_10m(collected_at)
        max_pages = max(1, int(os.getenv("MAX_PAGES_PER_COLLECTOR", "100")))
        seen_payloads: set[str] = set()
        pages = 0
        sent = 0
        started = time.monotonic()

        try:
            for page_number, items in enumerate(client.pages(endpoint), start=1):
                if page_number > max_pages:
                    COLLECTOR_PAGINATION_STOPS.labels(
                        event_type=event_type, reason="max_pages"
                    ).inc()
                    logging.warning(
                        "pagination stopped event_type=%s endpoint=%s page=%s "
                        "reason=max_pages limit=%s",
                        event_type, endpoint, page_number, max_pages,
                    )
                    break

                page_hash = payload_sha256(items)
                if page_hash in seen_payloads:
                    COLLECTOR_PAGINATION_STOPS.labels(
                        event_type=event_type, reason="repeated_payload"
                    ).inc()
                    logging.warning(
                        "pagination stopped event_type=%s endpoint=%s page=%s "
                        "reason=repeated_payload hash=%s",
                        event_type, endpoint, page_number, page_hash,
                    )
                    break

                seen_payloads.add(page_hash)
                pages += 1
                COLLECTOR_PAGES_COLLECTED.labels(event_type=event_type).inc()

                if not items:
                    continue

                is_new = ingest.send(
                    event_type=event_type,
                    items=items,
                    batch_id=batch_id_for(event_type, bucket_at, page_number, page_hash),
                    page=page_number,
                    collected_at=collected_at,
                )
                result = "accepted" if is_new else "duplicate"
                COLLECTOR_BATCHES_SENT.labels(event_type=event_type, result=result).inc()
                sent += int(is_new)

            COLLECTOR_LAST_SUCCESS.labels(event_type=event_type).set_to_current_time()
            span.set_attribute("argos.pages", pages)
            span.set_attribute("argos.batches_sent", sent)
            logging.info(
                "collector event_type=%s endpoint=%s pages=%s sent=%s",
                event_type, endpoint, pages, sent,
            )
            return pages, sent
        except IngestRejected as exc:
            COLLECTOR_BATCHES_SENT.labels(event_type=event_type, result="rejected").inc()
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            COLLECTOR_COLLECTION_DURATION.labels(event_type=event_type).observe(
                time.monotonic() - started
            )


async def run_cycle(ingest: IngestClient) -> None:
    with tracer.start_as_current_span("argos.collector_cycle") as span:
        concurrency = max(1, int(os.getenv("COLLECTOR_CONCURRENCY", "3")))
        semaphore = asyncio.Semaphore(concurrency)
        had_error = False

        async def run_one(event_type: str, endpoint: str) -> None:
            nonlocal had_error
            async with semaphore:
                try:
                    await asyncio.to_thread(collect_endpoint, event_type, endpoint, ingest)
                except Exception as exc:
                    had_error = True
                    span.record_exception(exc)
                    logging.exception(
                        "collector failed event_type=%s endpoint=%s", event_type, endpoint
                    )

        await asyncio.gather(*(run_one(n, e) for n, e in STATIC_ENDPOINTS.items()))
        status = "failed" if had_error else "success"
        COLLECTOR_CYCLES.labels(status=status).inc()
        span.set_attribute("argos.cycle_status", status)
        if had_error:
            span.set_status(Status(StatusCode.ERROR, "one or more endpoints failed"))


async def main() -> None:
    metrics_port = max(1, int(os.getenv("COLLECTOR_METRICS_PORT", "9101")))
    start_http_server(metrics_port)
    logging.info("collector metrics listening port=%s", metrics_port)

    ingest = IngestClient()
    interval = max(60, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "600")))
    while True:
        started = time.monotonic()
        await run_cycle(ingest)
        elapsed = time.monotonic() - started
        await asyncio.sleep(max(10, interval - elapsed))


if __name__ == "__main__":
    asyncio.run(main())
