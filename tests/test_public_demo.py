"""Coletor de demonstração (USGS e Open-Meteo) contra o contrato real da plataforma."""
from __future__ import annotations

import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "collectors" / "public-demo"
FIXTURES = Path(__file__).parent / "fixtures"

sys.path.insert(0, str(DEMO))
os.environ["SCHEMAS_DIR"] = str(DEMO / "schemas")

runtime_stub = types.ModuleType("app.observability.runtime")
runtime_stub.configure_observability = lambda service_name: None
sys.modules["app.observability.runtime"] = runtime_stub

import openmeteo  # noqa: E402
import run  # noqa: E402
import usgs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ingest import main as ingest  # noqa: E402
from app.ingest.contract import SchemaRegistry, resolve  # noqa: E402
from app.ingest.keys import CollectorIdentity  # noqa: E402
from app.store import clickhouse as store  # noqa: E402

BUILTIN = ROOT / "app" / "ingest" / "schemas"
registry = SchemaRegistry(BUILTIN, DEMO / "schemas")


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_usgs_parse_keeps_geojson_features():
    items = usgs.parse(fixture("usgs_sample.json"))
    assert len(items) == 3
    assert all(item["id"] and "properties" in item for item in items)


def test_usgs_items_validate_and_map_nested_fields():
    items = usgs.parse(fixture("usgs_sample.json"))
    assert registry.validate("earthquakes", "1", items) == []
    mapping = registry.mapping("earthquakes", "1")
    resolved = resolve(mapping, items[0])
    assert resolved.entity_id == items[0]["id"]
    assert resolved.name == items[0]["properties"]["place"]
    assert resolved.status == items[0]["properties"]["status"]
    assert resolved.dimensions["type"] == "earthquake"
    assert "magnitude" in resolved.dimensions


def test_usgs_drops_features_without_id():
    document = {"features": [{"id": "a", "properties": {}}, {"properties": {}}, "lixo"]}
    assert [f["id"] for f in usgs.parse(document)] == ["a"]


def test_openmeteo_parse_builds_flat_items_per_city():
    items = openmeteo.parse(fixture("openmeteo_sample.json"))
    assert [i["id"] for i in items] == ["sao-paulo", "rio-de-janeiro"]
    sp = items[0]
    assert sp["name"] == "São Paulo" and sp["region"] == "Sudeste" and sp["country"] == "BR"
    assert isinstance(sp["temperature_c"], float)
    assert sp["condition"] == openmeteo.condition(sp["weather_code"])


def test_openmeteo_items_validate_and_map():
    items = openmeteo.parse(fixture("openmeteo_sample.json"))
    assert registry.validate("weather", "1", items) == []
    resolved = resolve(registry.mapping("weather", "1"), items[1])
    assert (resolved.entity_id, resolved.name) == ("rio-de-janeiro", "Rio de Janeiro")
    assert resolved.dimensions == {"region": "Sudeste", "state": "RJ", "country": "BR"}
    assert resolved.status == items[1]["condition"]


@pytest.mark.parametrize("code,expected", [
    (0, "céu limpo"), (2, "nublado"), (45, "neblina"), (53, "garoa"), (63, "chuva"),
    (81, "chuva"), (73, "neve"), (95, "tempestade"), (None, "desconhecido"),
])
def test_weather_condition_categories(code, expected):
    assert openmeteo.condition(code) == expected


def test_batch_id_is_deterministic_per_content_and_bucket():
    bucket = datetime(2026, 10, 24, 19, 40)
    a = run.batch_id_for("usgs", "earthquakes", bucket, 1, [{"id": "x"}])
    assert a == run.batch_id_for("usgs", "earthquakes", bucket, 1, [{"id": "x"}])
    assert a != run.batch_id_for("usgs", "earthquakes", bucket, 1, [{"id": "y"}])
    assert a != run.batch_id_for("usgs", "earthquakes", bucket, 2, [{"id": "x"}])
    assert a != run.batch_id_for("usgs", "earthquakes", datetime(2026, 10, 24, 19, 50), 1, [{"id": "x"}])


def test_chunking():
    assert [len(c) for c in run.chunks([{}] * 5, 2)] == [2, 2, 1]


# ------------------------------------------------------ ponta a ponta (API real)


@pytest.fixture()
def platform(monkeypatch):
    enqueued: list[dict] = []
    monkeypatch.setattr(ingest, "registry", registry)
    monkeypatch.setattr(ingest, "enqueue_event", lambda **kw: enqueued.append(kw) or True)
    monkeypatch.setattr(
        ingest.keystore, "authenticate",
        lambda raw: CollectorIdentity("k", "demo", "default", frozenset({"earthquakes", "weather"}), "collector"),
    )
    client = TestClient(ingest.app)
    client.enqueued = enqueued
    return client


class ApiAsSession:
    """Faz o IngestClient do coletor falar com o TestClient em vez da rede."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.headers: dict[str, str] = {}

    def post(self, url, json=None, timeout=None, verify=None):
        return self.client.post("/v1/events", json=json, headers=self.headers)


def test_collector_output_is_accepted_by_the_platform_and_maps_to_rows(platform):
    from ingest_client import IngestClient

    ingest_client = IngestClient("http://ingest:8000", "key")
    ingest_client.session = ApiAsSession(platform)
    ingest_client.session.headers["X-API-Key"] = "key"

    class Job:
        EVENT_TYPE, SOURCE = "weather", "open-meteo"

        @staticmethod
        def fetch(_http):
            return openmeteo.parse(fixture("openmeteo_sample.json"))

    assert run.run_job(Job, None, ingest_client) == 2
    (queued,) = platform.enqueued
    assert (queued["source"], queued["event_type"], queued["tenant_id"]) == ("open-meteo", "weather", "default")

    message = {
        "tenant_id": queued["tenant_id"], "source": queued["source"],
        "collector_name": queued["event_type"], "schema_version": queued["schema_version"],
        "batch_id": queued["batch_id"], "collected_at": queued["collected_at"],
        "bucket_at": queued["bucket_at"],
    }
    rows = store.build_rows(message, queued["items"], registry)
    row = dict(zip(store.EVENT_COLUMNS, rows[0]))
    assert row["entity_id"] == "sao-paulo"
    assert row["dimensions"]["region"] == "Sudeste"
    assert json.loads(row["payload"])["name"] == "São Paulo"


def test_platform_rejects_a_malformed_weather_item(platform):
    from ingest_client import IngestClient, IngestRejected

    ingest_client = IngestClient("http://ingest:8000", "key")
    ingest_client.session = ApiAsSession(platform)
    ingest_client.session.headers["X-API-Key"] = "key"
    with pytest.raises(IngestRejected) as error:
        ingest_client.send("open-meteo", "weather", [{"id": "x"}], "b", 1, datetime.now(timezone.utc).replace(tzinfo=None))
    assert "422" in str(error.value)
