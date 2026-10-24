from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prometheus_client import start_http_server

from app.ingest.contract import SchemaRegistry, default_registry
from app.observability.metrics import (
    WORKER_ITEMS_PROCESSED,
    WORKER_MESSAGES,
    WORKER_PROCESSING_DURATION,
    WORKER_RECORDS_WRITTEN,
    WORKER_STALE_RECOVERED,
)
from app.observability.runtime import configure_observability
from app.queue import (
    ack,
    claim_stale,
    dead_letter,
    ensure_group,
    read_new,
    should_give_up,
    update_queue_metrics,
)
from app.store.clickhouse import ClickHouseSink

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

tracer = trace.get_tracer("argos.worker")


def parse_payload(value) -> list[dict]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("queue payload must be a JSON list")
    return value


def handle_message(message: dict[str, Any], sink: ClickHouseSink) -> None:
    """Processa uma mensagem: grava no ClickHouse e confirma. Em falha, deixa pendente
    (será retomada por claim_stale) ou envia para a dead-letter ao esgotar as tentativas."""
    collector = message["collector_name"]
    started = time.monotonic()
    with tracer.start_as_current_span(
        "argos.process_message",
        attributes={
            "argos.event_type": collector,
            "argos.source": message["source"],
            "argos.tenant_id": message["tenant_id"],
            "argos.queue_id": message["id"],
            "argos.attempts": int(message["attempts"]),
        },
    ) as span:
        try:
            items = parse_payload(message["payload"])
            span.set_attribute("argos.batch_size", len(items))
            written = sink.write(message, items)
            ack(message["id"])
            WORKER_MESSAGES.labels(collector=collector, status="processed").inc()
            WORKER_ITEMS_PROCESSED.labels(collector=collector).inc(len(items))
            WORKER_RECORDS_WRITTEN.labels(collector=collector).inc(written)
            span.set_attribute("argos.records_written", written)
            logging.info(
                "processed id=%s event_type=%s source=%s items=%s written=%s attempts=%s",
                message["id"], collector, message["source"], len(items), written,
                message["attempts"],
            )
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            logging.exception("worker failed id=%s event_type=%s", message["id"], collector)
            if should_give_up(message["attempts"]):
                dead_letter(message, repr(exc))
                WORKER_MESSAGES.labels(collector=collector, status="dead").inc()
                span.set_attribute("argos.final_status", "dead")
            else:
                WORKER_MESSAGES.labels(collector=collector, status="failed").inc()
        finally:
            WORKER_PROCESSING_DURATION.labels(collector=collector).observe(
                time.monotonic() - started
            )


def main() -> None:
    configure_observability("worker")
    registry: SchemaRegistry = default_registry()
    sink = ClickHouseSink(registry)
    ensure_group()

    metrics_port = max(1, int(os.getenv("WORKER_METRICS_PORT", "9102")))
    start_http_server(metrics_port)
    logging.info("worker metrics listening port=%s", metrics_port)

    batch = max(1, int(os.getenv("WORKER_BATCH_SIZE", "10")))
    block_ms = max(100, int(os.getenv("WORKER_POLL_SECONDS", "2")) * 1000)
    retry_idle_ms = max(1000, int(os.getenv("QUEUE_RETRY_SECONDS", "30")) * 1000)
    recover_every = max(5, int(os.getenv("QUEUE_RECOVER_EVERY_SECONDS", "30")))
    queue_metrics_every = max(10, int(os.getenv("QUEUE_METRICS_INTERVAL_SECONDS", "30")))
    last_recovery = 0.0
    last_queue_metrics = 0.0

    while True:
        now = time.monotonic()
        if now - last_recovery >= recover_every:
            stale = claim_stale(retry_idle_ms, batch)
            if stale:
                WORKER_STALE_RECOVERED.inc(len(stale))
                logging.warning("reclaimed pending messages=%s", len(stale))
                for message in stale:
                    handle_message(message, sink)
            last_recovery = now

        if now - last_queue_metrics >= queue_metrics_every:
            try:
                update_queue_metrics()
            except Exception:
                logging.exception("failed to update queue metrics")
            last_queue_metrics = now

        for message in read_new(batch, block_ms):
            handle_message(message, sink)


if __name__ == "__main__":
    main()
