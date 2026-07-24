from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from app.api import ArubaClient
from app.db import connection
from app.queue import enqueue_page


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

STATIC_ENDPOINTS = {
    "aps": "network-monitoring/v1/aps",
    "clients": "network-monitoring/v1/clients",
    "switches": "network-monitoring/v1/switches",
    "radios": "network-monitoring/v1/radios",
    "alerts": "network-notifications/v1/alerts",
    "licenses": "platform/licensing/v1/subscriptions",
    "insights_global": "aiops/v2/insights/global/list",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(value: datetime | None = None) -> datetime:
    value = value or utc_now()
    return value.replace(minute=(value.minute // 10) * 10, second=0, microsecond=0)


def known_site_ids() -> list[str]:
    sql = """
    SELECT DISTINCT site_id
      FROM (
        SELECT site_id FROM ap_current WHERE site_id IS NOT NULL AND site_id <> ''
        UNION
        SELECT site_id FROM raw_entity_current
         WHERE site_id IS NOT NULL AND site_id <> ''
      ) s
    """
    try:
        with connection() as cnx:
            cur = cnx.cursor()
            cur.execute(sql)
            return [str(row[0]) for row in cur.fetchall()]
    except Exception:
        logging.exception("could not load known site ids")
        return []


def endpoint_plan() -> list[tuple[str, str]]:
    plan = list(STATIC_ENDPOINTS.items())
    for site_id in known_site_ids():
        plan.append((f"insights_site:{site_id}", f"aiops/v2/insights/site/{site_id}/list"))
    return plan


def collect_endpoint(collector_name: str, endpoint: str) -> tuple[int, int]:
    client = ArubaClient()
    collected_at = utc_now()
    bucket_at = bucket_10m(collected_at)
    pages = 0
    queued = 0

    for page_number, items in enumerate(client.pages(endpoint), start=1):
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
        collector_name, endpoint, pages, queued,
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
