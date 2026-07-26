from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

from prometheus_client import start_http_server

from app.api import ArubaClient
from app.observability.metrics import (
    PRODUCER_COLLECTION_DURATION,
    PRODUCER_CYCLES,
    PRODUCER_LAST_SUCCESS,
    PRODUCER_PAGES_COLLECTED,
    PRODUCER_PAGES_QUEUED,
    PRODUCER_PAGINATION_STOPS,
)
from app.queue import enqueue_page


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

# Licensing and AI Insights stay disabled until the customer explicitly requests
# them and the corresponding New Central endpoints are validated for the tenant.
STATIC_ENDPOINTS = {
    "aps": "network-monitoring/v1/aps",
    "clients": "network-monitoring/v1/clients",
    "switches": "network-monitoring/v1/switches",
    "radios": "network-monitoring/v1/radios",
    "alerts": "network-notifications/v1/alerts",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(value: datetime | None = None) -> datetime:
    value = value or utc_now()
    return value.replace(minute=(value.minute // 10) * 10, second=0, microsecond=0)


def endpoint_plan() -> list[tuple[str, str]]:
    return list(STATIC_ENDPOINTS.items())


def payload_sha256(items: list) -> str:
    canonical = json.dumps(
        items,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def collect_endpoint(collector_name: str, endpoint: str) -> tuple[int, int]:
    client = ArubaClient()
    collected_at = utc_now()
    bucket_at = bucket_10m(collected_at)
    max_pages = max(1, int(os.getenv("MAX_PAGES_PER_COLLECTOR", "100")))
    seen_payloads: set[str] = set()
    pages = 0
    queued = 0
    started = time.monotonic()

    try:
        for page_number, items in enumerate(client.pages(endpoint), start=1):
            if page_number > max_pages:
                PRODUCER_PAGINATION_STOPS.labels(
                    collector=collector_name,
                    reason="max_pages",
                ).inc()
                logging.warning(
                    "producer pagination stopped collector=%s endpoint=%s "
                    "page=%s reason=max_pages limit=%s",
                    collector_name,
                    endpoint,
                    page_number,
                    max_pages,
                )
                break

            page_hash = payload_sha256(items)
            if page_hash in seen_payloads:
                PRODUCER_PAGINATION_STOPS.labels(
                    collector=collector_name,
                    reason="repeated_payload",
                ).inc()
                logging.warning(
                    "producer pagination stopped collector=%s endpoint=%s "
                    "page=%s reason=repeated_payload hash=%s",
                    collector_name,
                    endpoint,
                    page_number,
                    page_hash,
                )
                break

            seen_payloads.add(page_hash)
            pages += 1
            PRODUCER_PAGES_COLLECTED.labels(collector=collector_name).inc()

            if enqueue_page(
                collector_name=collector_name,
                endpoint=endpoint,
                page_number=page_number,
                collected_at=collected_at,
                bucket_at=bucket_at,
                items=items,
            ):
                queued += 1
                PRODUCER_PAGES_QUEUED.labels(collector=collector_name).inc()

        PRODUCER_LAST_SUCCESS.labels(collector=collector_name).set_to_current_time()
        logging.info(
            "producer collector=%s endpoint=%s pages=%s queued=%s",
            collector_name,
            endpoint,
            pages,
            queued,
        )
        return pages, queued
    finally:
        PRODUCER_COLLECTION_DURATION.labels(collector=collector_name).observe(
            time.monotonic() - started
        )


async def run_cycle() -> None:
    concurrency = max(1, int(os.getenv("PRODUCER_CONCURRENCY", "3")))
    semaphore = asyncio.Semaphore(concurrency)
    had_error = False

    async def run_one(name: str, endpoint: str) -> None:
        nonlocal had_error
        async with semaphore:
            try:
                await asyncio.to_thread(collect_endpoint, name, endpoint)
            except Exception:
                had_error = True
                logging.exception("producer failed collector=%s endpoint=%s", name, endpoint)

    await asyncio.gather(*(run_one(name, endpoint) for name, endpoint in endpoint_plan()))
    PRODUCER_CYCLES.labels(status="failed" if had_error else "success").inc()


async def main() -> None:
    metrics_port = max(1, int(os.getenv("PRODUCER_METRICS_PORT", "9101")))
    start_http_server(metrics_port)
    logging.info("producer metrics listening port=%s", metrics_port)

    interval = max(60, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "600")))
    while True:
        started = time.monotonic()
        await run_cycle()
        elapsed = time.monotonic() - started
        await asyncio.sleep(max(10, interval - elapsed))


if __name__ == "__main__":
    asyncio.run(main())
