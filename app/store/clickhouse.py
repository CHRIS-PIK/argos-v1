from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.processors import entity_id
from app.utils import first, utc_now

EVENT_COLUMNS = [
    "tenant_id", "source", "event_type", "schema_version", "entity_id", "bucket_at",
    "collected_at", "ingested_at", "site_id", "site_name", "entity_name", "status",
    "batch_id", "payload",
]
LATEST_COLUMNS = [c for c in EVENT_COLUMNS if c != "bucket_at"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def build_rows(message: dict[str, Any], items: list[dict[str, Any]]) -> list[list[Any]]:
    """Converte os itens de uma mensagem da fila em linhas da tabela events.

    As mesmas linhas alimentam entity_latest (sem a coluna bucket_at).
    """
    ingested_at = _utc(utc_now())
    collected_at = _utc(message["collected_at"])
    bucket_at = _utc(message["bucket_at"])
    rows = []
    for item in items:
        item_id = entity_id(item)
        if not item_id:
            continue
        rows.append([
            message.get("tenant_id") or "default",
            message["source"],
            message["collector_name"],
            str(message.get("schema_version") or "1"),
            item_id,
            bucket_at,
            collected_at,
            ingested_at,
            str(first(item, "siteId", default="") or ""),
            str(first(item, "siteName", default="") or ""),
            str(first(item, "deviceName", "name", "title", "subscriptionName",
                      "insightName", "alertName", default="") or ""),
            str(first(item, "status", "state", "severity", default="") or ""),
            message.get("batch_id") or "",
            json.dumps(item, ensure_ascii=False, separators=(",", ":")),
        ])
    return rows


class ClickHouseSink:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import clickhouse_connect

            self._client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_USER", "default"),
                password=os.getenv("CLICKHOUSE_PASSWORD", ""),
                database=os.getenv("CLICKHOUSE_DATABASE", "argos"),
            )
        return self._client

    def write(self, message: dict[str, Any], items: list[dict[str, Any]]) -> int:
        rows = build_rows(message, items)
        if not rows:
            return 0
        self.client.insert("events", rows, column_names=EVENT_COLUMNS)
        latest = [[row[i] for i, c in enumerate(EVENT_COLUMNS) if c != "bucket_at"] for row in rows]
        self.client.insert("entity_latest", latest, column_names=LATEST_COLUMNS)
        return len(rows) * 2


def enabled() -> bool:
    return os.getenv("CLICKHOUSE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
