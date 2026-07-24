from __future__ import annotations

import json
import logging
import os
import time

from app.processors import process_message
from app.queue import claim_message, mark_failed, mark_processed, recover_stale_messages


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)


def parse_payload(value) -> list[dict]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("queue payload must be a JSON list")
    return value


def main() -> None:
    poll_seconds = max(1, int(os.getenv("WORKER_POLL_SECONDS", "2")))
    lock_timeout = max(60, int(os.getenv("QUEUE_LOCK_TIMEOUT_SECONDS", "900")))
    recover_every = max(30, int(os.getenv("QUEUE_RECOVER_EVERY_SECONDS", "60")))
    last_recovery = 0.0

    while True:
        now = time.monotonic()
        if now - last_recovery >= recover_every:
            recovered = recover_stale_messages(lock_timeout)
            if recovered:
                logging.warning("recovered stale queue messages=%s", recovered)
            last_recovery = now

        message = claim_message()
        if not message:
            time.sleep(poll_seconds)
            continue

        try:
            items = parse_payload(message["payload"])
            written = process_message(
                collector_name=message["collector_name"],
                items=items,
                collected_at=message["collected_at"],
                bucket_at=message["bucket_at"],
            )
            mark_processed(message["id"])
            logging.info(
                "processed queue_id=%s collector=%s items=%s written=%s attempts=%s",
                message["id"], message["collector_name"], len(items),
                written, message["attempts"],
            )
        except Exception as exc:
            logging.exception(
                "worker failed queue_id=%s collector=%s",
                message["id"], message["collector_name"],
            )
            mark_failed(message["id"], message["attempts"], repr(exc))


if __name__ == "__main__":
    main()
