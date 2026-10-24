from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from pathlib import Path

ARUBA_SCHEMAS = Path(__file__).resolve().parents[1] / "collectors" / "aruba" / "schemas"
os.environ["SCHEMAS_DIR"] = str(ARUBA_SCHEMAS)

# O runtime de observabilidade exige OTLP/Pyroscope; nos testes basta um no-op.
runtime_stub = types.ModuleType("app.observability.runtime")
runtime_stub.configure_observability = lambda service_name: None
sys.modules["app.observability.runtime"] = runtime_stub

from fastapi.testclient import TestClient  # noqa: E402

from app.ingest import main as ingest  # noqa: E402
from app.ingest.keys import CollectorIdentity  # noqa: E402

API_KEY = "argos_test_key"


def identity(allowed=("*",)) -> CollectorIdentity:
    return CollectorIdentity(
        key_id="k1", name="test", tenant_id="acme", allowed_event_types=frozenset(allowed)
    )


@pytest.fixture()
def client(monkeypatch):
    enqueued: list[dict] = []
    seen: set[tuple] = set()

    def fake_enqueue(**kwargs) -> bool:
        key = (kwargs["tenant_id"], kwargs["source"], kwargs["event_type"],
               kwargs["batch_id"], kwargs["page_number"])
        enqueued.append(kwargs)
        if key in seen:
            return False
        seen.add(key)
        return True

    monkeypatch.setattr(ingest, "enqueue_event", fake_enqueue)
    monkeypatch.setattr(
        ingest.keystore,
        "authenticate",
        lambda raw: identity() if raw == API_KEY else None,
    )
    test_client = TestClient(ingest.app)
    test_client.enqueued = enqueued
    return test_client


def body(**overrides) -> dict:
    payload = {
        "source": "aruba-central",
        "event_type": "aps",
        "schema_version": "1",
        "batch_id": "b1",
        "page": 1,
        "items": [{"id": "ap-1", "status": "Up"}],
    }
    payload.update(overrides)
    return payload


def post(client, payload, key=API_KEY):
    headers = {"X-API-Key": key} if key else {}
    return client.post("/v1/events", json=payload, headers=headers)


def test_accepts_valid_batch(client):
    response = post(client, body())
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "duplicate": False, "items": 1}
    queued = client.enqueued[0]
    assert queued["tenant_id"] == "acme"
    assert queued["event_type"] == "aps"
    assert queued["source"] == "aruba-central"


def test_resend_is_reported_as_duplicate(client):
    assert post(client, body()).json()["duplicate"] is False
    assert post(client, body()).json()["duplicate"] is True


def test_requires_api_key(client):
    assert post(client, body(), key=None).status_code == 401
    assert post(client, body(), key="wrong").status_code == 401


def test_unknown_event_type_is_rejected(client):
    response = post(client, body(event_type="nope"))
    assert response.status_code == 422
    assert "no schema registered" in response.json()["detail"]
    assert client.enqueued == []


def test_item_without_identifier_is_rejected(client):
    response = post(client, body(items=[{"status": "Up"}]))
    assert response.status_code == 422
    assert response.json()["detail"][0].startswith("items[0]")
    assert "entity_id" in response.json()["detail"][0]


def test_empty_items_is_rejected(client):
    assert post(client, body(items=[])).status_code == 422


def test_invalid_names_are_rejected(client):
    assert post(client, body(source="Bad Source!")).status_code == 422


def test_key_scoped_to_event_types(client, monkeypatch):
    monkeypatch.setattr(
        ingest.keystore, "authenticate", lambda raw: identity(allowed=("clients",))
    )
    assert post(client, body(event_type="aps")).status_code == 403
    assert post(client, body(event_type="clients")).status_code == 202


def test_batch_size_limit(client, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_ITEMS_PER_BATCH", 2)
    items = [{"id": str(i)} for i in range(3)]
    assert post(client, body(items=items)).status_code == 413


def test_collected_at_bounds(client):
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=1)).isoformat()
    old = (now - timedelta(days=3)).isoformat()
    assert post(client, body(collected_at=future)).status_code == 422
    assert post(client, body(collected_at=old)).status_code == 422
    assert post(client, body(collected_at=now.isoformat(), batch_id="ok")).status_code == 202


def test_bucket_is_floored_to_ten_minutes(client):
    stamp = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(minute=47, second=31, microsecond=0)
    post(client, body(collected_at=stamp.isoformat(), batch_id="bucket"))
    assert client.enqueued[-1]["bucket_at"].minute == 40
    assert client.enqueued[-1]["bucket_at"].second == 0


def test_schema_catalog_lists_known_types(client):
    response = client.get("/v1/schemas", headers={"X-API-Key": API_KEY})
    types_ = {entry["event_type"] for entry in response.json()["schemas"]}
    assert {"aps", "clients", "switches", "radios", "alerts", "generic"} <= types_


def test_health_and_metrics(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert b"argos_ingest_requests_total" in client.get("/metrics").content
