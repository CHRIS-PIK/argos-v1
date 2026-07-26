from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

from app.api import ArubaClient
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

    for page_number, items in enumerate(client.pages(endpoint), start=1):
        if page_number > max_pages:
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

        if enqueue_page(
            collector_name=collector_name,
            endpoint=endpoint,
            page_number=page_number,
            collected_at=collected_at,
            bucket_at=bucket_at,
            items=items,
        ):
            queued += 1

    logging.info(
        "producer collector=%s endpoint=%s pages=%s queued=%s",
        collector_name,
        endpoint,
        pages,
        queued,
    )
    return pages, queued


async def run_cycle() -> None:
    concurrency = max(1, int(os.getenv("PRODUCER_CONCURRENCY", "3")))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(name: str, endpoint: str) -> None:
        async with semaphore:
            try:
                await asyncio.to_thread(collect_endpoint, name, endpoint)
            except Exception:
                logging.exception("producer failed collector=%s endpoint=%s", name, endpoint)

    await asyncio.gather(*(run_one(name, endpoint) for name, endpoint in endpoint_plan()))


async def main() -> None:
    interval = max(60, int(os.getenv("COLLECTION_INTERVAL_SECONDS", "600")))
    while True:
        started = time.monotonic()
        await run_cycle()
        elapsed = time.monotonic() - started
        await asyncio.sleep(max(10, interval - elapsed))


if __name__ == "__main__":
    asyncio.run(main())
