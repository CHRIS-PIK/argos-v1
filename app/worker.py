from __future__ import annotations

import json
import logging
import os
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import start_http_server

from app.observability.metrics import (
    WORKER_ITEMS_PROCESSED,
    WORKER_MESSAGES,
    WORKER_PROCESSING_DURATION,
    WORKER_RECORDS_WRITTEN,
    WORKER_STALE_RECOVERED,
)
from app.observability.runtime import configure_observability
from app.processors import process_message
from app.queue import (
    claim_message,
    mark_failed,
    mark_processed,
    recover_stale_messages,
    update_queue_metrics,
)


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

configure_observability("worker")
tracer = trace.get_tracer("argos.worker")


def parse_payload(value) -> list[dict]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("queue payload must be a JSON list")
    return value


def main() -> None:
    metrics_port = max(1, int(os.getenv("WORKER_METRICS_PORT", "9102")))
    start_http_server(metrics_port)
    logging.info("worker metrics listening port=%s", metrics_port)

    poll_seconds = max(1, int(os.getenv("WORKER_POLL_SECONDS", "2")))
    lock_timeout = max(60, int(os.getenv("QUEUE_LOCK_TIMEOUT_SECONDS", "900")))
    recover_every = max(30, int(os.getenv("QUEUE_RECOVER_EVERY_SECONDS", "60")))
    queue_metrics_every = max(10, int(os.getenv("QUEUE_METRICS_INTERVAL_SECONDS", "30")))
    last_recovery = 0.0
    last_queue_metrics = 0.0

    while True:
        now = time.monotonic()
        if now - last_recovery >= recover_every:
            recovered = recover_stale_messages(lock_timeout)
            if recovered:
                WORKER_STALE_RECOVERED.inc(recovered)
                logging.warning("recovered stale queue messages=%s", recovered)
            last_recovery = now

        if now - last_queue_metrics >= queue_metrics_every:
            try:
                update_queue_metrics()
            except Exception:
                logging.exception("failed to update queue metrics")
            last_queue_metrics = now

        message = claim_message()
        if not message:
            time.sleep(poll_seconds)
            continue

        collector = message["collector_name"]
        started = time.monotonic()
        with tracer.start_as_current_span(
            "argos.process_message",
            attributes={
                "argos.collector": collector,
                "argos.queue_id": str(message["id"]),
                "argos.attempts": int(message["attempts"]),
            },
        ) as span:
            try:
                items = parse_payload(message["payload"])
                span.set_attribute("argos.batch_size", len(items))
                written = process_message(
                    collector_name=collector,
                    items=items,
                    collected_at=message["collected_at"],
                    bucket_at=message["bucket_at"],
                )
                mark_processed(message["id"])
                WORKER_MESSAGES.labels(collector=collector, status="processed").inc()
                WORKER_ITEMS_PROCESSED.labels(collector=collector).inc(len(items))
                WORKER_RECORDS_WRITTEN.labels(collector=collector).inc(written)
                span.set_attribute("argos.records_written", written)
                logging.info(
                    "processed queue_id=%s collector=%s items=%s written=%s attempts=%s",
                    message["id"],
                    collector,
                    len(items),
                    written,
                    message["attempts"],
                )
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logging.exception(
                    "worker failed queue_id=%s collector=%s",
                    message["id"],
                    collector,
                )
                final_status = mark_failed(message["id"], message["attempts"], repr(exc))
                WORKER_MESSAGES.labels(
                    collector=collector,
                    status=final_status.lower(),
                ).inc()
                span.set_attribute("argos.final_status", final_status.lower())
            finally:
                WORKER_PROCESSING_DURATION.labels(collector=collector).observe(
                    time.monotonic() - started
                )


if __name__ == "__main__":
    main()
