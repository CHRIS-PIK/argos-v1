from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.ingest.contract import SchemaRegistry, resolve
from app.queue import utc_now

EVENT_COLUMNS = [
    "tenant_id", "source", "event_type", "schema_version", "entity_id", "bucket_at",
    "collected_at", "ingested_at", "name", "status", "dimensions", "batch_id", "payload",
]
LATEST_COLUMNS = [c for c in EVENT_COLUMNS if c != "bucket_at"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def build_rows(
    message: dict[str, Any],
    items: list[dict[str, Any]],
    registry: SchemaRegistry,
) -> list[list[Any]]:
    """Converte os itens de uma mensagem em linhas de `events`, usando o mapeamento do schema.

    As mesmas linhas alimentam `entity_latest` (sem a coluna bucket_at).
    """
    event_type = message["collector_name"]
    version = str(message.get("schema_version") or "1")
    mapping = registry.mapping(event_type, version)

    ingested_at = _utc(utc_now())
    collected_at = _utc(message["collected_at"])
    bucket_at = _utc(message["bucket_at"])
    rows = []
    for item in items:
        resolved = resolve(mapping, item)
        if resolved is None:
            continue
        rows.append([
            message.get("tenant_id") or "default",
            message["source"],
            event_type,
            version,
            resolved.entity_id,
            bucket_at,
            collected_at,
            ingested_at,
            resolved.name,
            resolved.status,
            resolved.dimensions,
            message.get("batch_id") or "",
            json.dumps(item, ensure_ascii=False, separators=(",", ":")),
        ])
    return rows


class ClickHouseSink:
    def __init__(self, registry: SchemaRegistry, client: Any | None = None) -> None:
        self.registry = registry
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
        rows = build_rows(message, items, self.registry)
        if not rows:
            return 0
        self.client.insert("events", rows, column_names=EVENT_COLUMNS)
        latest = [
            [value for column, value in zip(EVENT_COLUMNS, row) if column != "bucket_at"]
            for row in rows
        ]
        self.client.insert("entity_latest", latest, column_names=LATEST_COLUMNS)
        return len(rows)
