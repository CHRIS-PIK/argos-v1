from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone

from pathlib import Path  # noqa: E402

from app.ingest.contract import SchemaRegistry  # noqa: E402
from app.store import clickhouse as store  # noqa: E402

BUILTIN = Path(__file__).resolve().parents[1] / "app" / "ingest" / "schemas"
ARUBA = Path(__file__).resolve().parents[1] / "collectors" / "aruba" / "schemas"
registry = SchemaRegistry(BUILTIN, ARUBA)


def message(**overrides) -> dict:
    base = {
        "tenant_id": "acme",
        "source": "aruba-central",
        "collector_name": "aps",
        "schema_version": "1",
        "batch_id": "b1",
        "collected_at": datetime(2026, 10, 24, 19, 47, 31),
        "bucket_at": datetime(2026, 10, 24, 19, 40),
    }
    base.update(overrides)
    return base


class FakeClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, list, list]] = []

    def insert(self, table, rows, column_names):
        self.inserts.append((table, rows, column_names))


def test_build_rows_maps_message_and_item():
    item = {"id": "ap-1", "deviceName": "AP Sala", "siteId": "s1", "siteName": "HQ", "status": "Up"}
    rows = store.build_rows(message(), [item], registry)
    row = dict(zip(store.EVENT_COLUMNS, rows[0]))
    assert row["tenant_id"] == "acme"
    assert row["source"] == "aruba-central"
    assert row["event_type"] == "aps"
    assert row["entity_id"] == "ap-1"
    assert row["name"] == "AP Sala"
    assert row["dimensions"] == {"site_id": "s1", "site_name": "HQ"}
    assert row["status"] == "Up"
    assert row["batch_id"] == "b1"
    assert row["bucket_at"].tzinfo == timezone.utc
    assert '"id":"ap-1"' in row["payload"]


def test_items_without_identifier_are_skipped():
    assert store.build_rows(message(), [{"status": "Up"}], registry) == []


def test_defaults_for_legacy_messages():
    rows = store.build_rows(
        message(tenant_id=None, batch_id=None, schema_version=None), [{"id": "x"}], registry
    )
    row = dict(zip(store.EVENT_COLUMNS, rows[0]))
    assert (row["tenant_id"], row["batch_id"], row["schema_version"]) == ("default", "", "1")


def test_write_inserts_events_and_latest_without_bucket():
    client = FakeClient()
    written = store.ClickHouseSink(registry, client).write(message(), [{"id": "a"}, {"id": "b"}])
    assert written == 2
    (events_table, events, events_cols), (latest_table, latest, latest_cols) = client.inserts
    assert (events_table, latest_table) == ("events", "entity_latest")
    assert "bucket_at" in events_cols and "bucket_at" not in latest_cols
    assert all(len(r) == len(latest_cols) for r in latest)


def test_write_with_nothing_to_insert_skips_client():
    client = FakeClient()
    assert store.ClickHouseSink(registry, client).write(message(), [{"status": "Up"}]) == 0
    assert client.inserts == []


def test_sink_is_agnostic_to_the_source_schema():
    """Um tipo que nao e da Aruba passa pelo mesmo caminho, so com o schema generic."""
    only_generic = SchemaRegistry(BUILTIN)
    rows = store.build_rows(
        message(collector_name="generic", source="my-erp"),
        [{"id": "o-9", "name": "Pedido", "status": "open", "total": 10}],
        only_generic,
    )
    row = dict(zip(store.EVENT_COLUMNS, rows[0]))
    assert (row["source"], row["event_type"], row["entity_id"]) == ("my-erp", "generic", "o-9")
    assert row["dimensions"] == {}
    assert '"total":10' in row["payload"]
