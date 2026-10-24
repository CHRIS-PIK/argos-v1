"""Coletor de demonstração: busca APIs públicas e envia à Ingest API do Argos.

Serve de exemplo mínimo e de teste de ponta a ponta com fontes que não têm nada
a ver com a Aruba. Jobs ativos em DEMO_JOBS (padrão: usgs,openmeteo).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from types import ModuleType

import requests
from prometheus_client import Counter, Gauge, start_http_server

import openmeteo
import usgs
from ingest_client import IngestClient, IngestRejected

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

JOBS: dict[str, ModuleType] = {"usgs": usgs, "openmeteo": openmeteo}
CHUNK = max(1, int(os.getenv("DEMO_CHUNK_SIZE", "500")))

BATCHES = Counter(
    "argos_demo_batches_sent_total", "Lotes enviados, por resultado.", ["event_type", "result"]
)
ITEMS = Counter("argos_demo_items_collected_total", "Itens coletados.", ["event_type"])
LAST_SUCCESS = Gauge(
    "argos_demo_last_success_timestamp_seconds", "Última coleta bem-sucedida.", ["event_type"]
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bucket_10m(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 10) * 10, second=0, microsecond=0)


def payload_sha256(items: list[dict]) -> str:
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def batch_id_for(source: str, event_type: str, bucket_at: datetime, page: int, items: list[dict]) -> str:
    """Determinístico: reenviar o mesmo conteúdo no mesmo bucket é idempotente."""
    raw = f"{source}|{event_type}|{bucket_at.isoformat()}|{page}|{payload_sha256(items)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def chunks(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def run_job(job: ModuleType, http: requests.Session, ingest: IngestClient) -> int:
    items = job.fetch(http)
    collected_at = utc_now()
    bucket_at = bucket_10m(collected_at)
    ITEMS.labels(event_type=job.EVENT_TYPE).inc(len(items))

    sent = 0
    for page, part in enumerate(chunks(items, CHUNK), start=1):
        is_new = ingest.send(
            source=job.SOURCE,
            event_type=job.EVENT_TYPE,
            items=part,
            batch_id=batch_id_for(job.SOURCE, job.EVENT_TYPE, bucket_at, page, part),
            page=page,
            collected_at=collected_at,
        )
        BATCHES.labels(event_type=job.EVENT_TYPE, result="accepted" if is_new else "duplicate").inc()
        sent += int(is_new)

    LAST_SUCCESS.labels(event_type=job.EVENT_TYPE).set_to_current_time()
    logging.info("job=%s items=%s batches_new=%s", job.EVENT_TYPE, len(items), sent)
    return len(items)


def main() -> None:
    ingest = IngestClient(os.environ["ARGOS_INGEST_URL"], os.environ["ARGOS_API_KEY"])
    names = [n.strip() for n in os.getenv("DEMO_JOBS", "usgs,openmeteo").split(",") if n.strip()]
    unknown = [n for n in names if n not in JOBS]
    if unknown:
        raise SystemExit(f"DEMO_JOBS desconhecidos: {unknown}; opções: {sorted(JOBS)}")

    start_http_server(max(1, int(os.getenv("DEMO_METRICS_PORT", "9103"))))
    interval = max(60, int(os.getenv("DEMO_INTERVAL_SECONDS", "300")))
    http = requests.Session()
    http.headers["User-Agent"] = "argos-public-demo/1.0"

    while True:
        started = time.monotonic()
        for name in names:
            try:
                run_job(JOBS[name], http, ingest)
            except IngestRejected:
                BATCHES.labels(event_type=JOBS[name].EVENT_TYPE, result="rejected").inc()
                logging.exception("plataforma recusou o lote job=%s", name)
            except Exception:
                logging.exception("job falhou job=%s", name)
        time.sleep(max(10, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
