from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

ARUBA_SCHEMAS = Path(__file__).resolve().parents[1] / "collectors" / "aruba" / "schemas"
os.environ["SCHEMAS_DIR"] = str(ARUBA_SCHEMAS)

runtime_stub = types.ModuleType("app.observability.runtime")
runtime_stub.configure_observability = lambda service_name: None
sys.modules["app.observability.runtime"] = runtime_stub

from fastapi.testclient import TestClient  # noqa: E402

from app.ingest.keys import CollectorIdentity  # noqa: E402
from app.query import db, main as query  # noqa: E402
from app.query.filters import decode_cursor, encode_cursor  # noqa: E402

KEY = "reader-key"


def identity(role="reader", allowed=("*",), tenant="acme") -> CollectorIdentity:
    return CollectorIdentity(
        key_id="k", name="t", tenant_id=tenant, allowed_event_types=frozenset(allowed), role=role
    )


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.responses: list[list[dict]] = []

    def rows(self, sql, parameters):
        self.calls.append((sql, parameters))
        return self.responses.pop(0) if self.responses else []


@pytest.fixture()
def fake(monkeypatch):
    fake_db = FakeDb()
    monkeypatch.setattr(db, "rows", fake_db.rows)
    monkeypatch.setattr(query.keystore, "authenticate",
                        lambda raw: identity() if raw == KEY else None)
    return fake_db


@pytest.fixture()
def client(fake):
    return TestClient(query.app)


def get(client, path, api_key=KEY, **params):
    headers = {"X-API-Key": api_key} if api_key else {}
    return client.get(path, params=params, headers=headers)


def entity(i: int, **extra) -> dict:
    row = {
        "tenant_id": "acme", "event_type": "aps", "source": "aruba-central",
        "schema_version": "1", "entity_id": f"ap-{i:03d}", "name": f"AP {i}", "status": "Up",
        "dimensions": {"site_name": "HQ"},
        "collected_at": datetime(2026, 10, 24, 19, 40, tzinfo=timezone.utc),
        "ingested_at": datetime(2026, 10, 24, 19, 41, tzinfo=timezone.utc), "batch_id": "b",
    }
    row.update(extra)
    return row


def test_requires_api_key_and_reader_role(client, monkeypatch):
    assert get(client, "/v1/entities", api_key=None).status_code == 401
    assert get(client, "/v1/entities", api_key="bad").status_code == 401
    monkeypatch.setattr(query.keystore, "authenticate", lambda raw: identity(role="collector"))
    assert get(client, "/v1/entities").status_code == 403


def test_admin_can_read(client, monkeypatch):
    monkeypatch.setattr(query.keystore, "authenticate", lambda raw: identity(role="admin"))
    assert get(client, "/v1/entities").status_code == 200


def test_tenant_always_comes_from_the_key(client, fake):
    get(client, "/v1/entities", tenant="other")
    sql, params = fake.calls[0]
    assert params["tenant"] == "acme"
    assert "other" not in str(params)
    assert "tenant_id = {tenant:String}" in sql


def test_allowed_event_types_restrict_the_query(client, fake, monkeypatch):
    monkeypatch.setattr(query.keystore, "authenticate",
                        lambda raw: identity(allowed=("aps", "clients")))
    get(client, "/v1/entities")
    sql, params = fake.calls[0]
    assert "event_type IN {allowed:Array(String)}" in sql
    assert params["allowed"] == ["aps", "clients"]


def test_filters_are_bound_parameters_never_sql_text(client, fake):
    evil = "x' OR 1=1 --"
    get(client, "/v1/entities", source=evil, status="Down", q=evil, **{"dim.site_name": evil})
    sql, params = fake.calls[0]
    assert evil not in sql
    assert params["source"] == evil and params["status"] == "Down" and params["q"] == evil
    assert "dimensions[{dk0:String}] = {dv0:String}" in sql
    assert params["dk0"] == "site_name" and params["dv0"] == evil


def test_invalid_dimension_name_is_rejected(client):
    assert get(client, "/v1/entities", **{"dim.bad key": "v"}).status_code == 422


def test_pagination_returns_next_cursor_and_uses_keyset(client, fake):
    fake.responses.append([entity(i) for i in range(3)])  # limit=2 -> pede 3
    body = get(client, "/v1/entities", limit=2).json()
    assert [i["entity_id"] for i in body["items"]] == ["ap-000", "ap-001"]
    assert fake.calls[0][1]["limit"] == 3
    assert decode_cursor(body["next_cursor"], 3) == ["aps", "aruba-central", "ap-001"]

    fake.responses.append([entity(2)])
    last = get(client, "/v1/entities", limit=2, cursor=body["next_cursor"]).json()
    assert last["next_cursor"] is None
    sql, params = fake.calls[1]
    assert "(event_type, source, entity_id) > " in sql
    assert params["c2"] == "ap-001"


def test_bad_cursor_is_rejected(client):
    assert get(client, "/v1/entities", cursor="not-a-cursor").status_code == 422
    assert get(client, "/v1/entities", cursor=encode_cursor([1])).status_code == 422


def test_payload_only_when_requested(client, fake):
    fake.responses.append([entity(1, payload='{"id":"ap-001","cpu":3}')])
    item = get(client, "/v1/entities", include_payload="true").json()["items"][0]
    assert item["payload"] == {"id": "ap-001", "cpu": 3}
    assert ", payload" in fake.calls[0][0]

    fake.responses.append([entity(1)])
    item = get(client, "/v1/entities").json()["items"][0]
    assert "payload" not in item
    assert ", payload" not in fake.calls[1][0]


def test_datetimes_are_serialized_as_utc_iso(client, fake):
    fake.responses.append([entity(1)])
    item = get(client, "/v1/entities").json()["items"][0]
    assert item["collected_at"] == "2026-10-24T19:40:00Z"


def test_limit_is_capped(client):
    assert get(client, "/v1/entities", limit=5000).status_code == 422


def test_count(client, fake):
    fake.responses.append([{"total": 42}])
    assert get(client, "/v1/entities/count", status="Down").json() == {"total": 42}


def test_entity_detail_404_and_found(client, fake):
    args = dict(event_type="aps", source="aruba-central", entity_id="AA:BB")
    assert get(client, "/v1/entity", **args).status_code == 404

    fake.responses.append([entity(1, payload='{"id":"1"}')])
    fake.responses.append([entity(1, payload='{"id":"1"}', bucket_at=datetime(2026, 10, 24, 19, 40))])
    body = get(client, "/v1/entity", **args).json()
    assert body["entity"]["payload"] == {"id": "1"}
    assert len(body["history"]) == 1
    assert fake.calls[-1][1]["entity_id"] == "AA:BB"


def test_events_default_window_and_bounds(client, fake):
    assert get(client, "/v1/events").status_code == 200
    params = fake.calls[0][1]
    assert params["t_from"] < params["t_to"]
    assert (params["t_to"] - params["t_from"]).total_seconds() == 24 * 3600
    bad = get(client, "/v1/events", **{"from": "2026-10-24T10:00:00Z", "to": "2026-10-24T09:00:00Z"})
    assert bad.status_code == 422


def test_events_cursor_roundtrip(client, fake):
    row = entity(1, bucket_at=datetime(2026, 10, 24, 19, 40, tzinfo=timezone.utc))
    fake.responses.append([row, row])
    body = get(client, "/v1/events", limit=1).json()
    values = decode_cursor(body["next_cursor"], 4)
    assert values[0] == int(datetime(2026, 10, 24, 19, 40, tzinfo=timezone.utc).timestamp())
    get(client, "/v1/events", cursor=body["next_cursor"])
    sql, params = fake.calls[1]
    assert "(bucket_at, event_type, source, entity_id) < " in sql
    assert params["c0"] == values[0]


def test_meta_groups_by_type(client, fake):
    fake.responses += [
        [{"event_type": "aps", "source": "aruba-central", "entities": 3,
          "last_ingested": datetime(2026, 10, 24, 19, 41, tzinfo=timezone.utc)},
         {"event_type": "aps", "source": "other", "entities": 2,
          "last_ingested": datetime(2026, 10, 24, 19, 0, tzinfo=timezone.utc)}],
        [{"event_type": "aps", "statuses": ["Up", "", "Down"]}],
        [{"event_type": "aps", "key": "site_name", "distinct_values": 4}],
    ]
    body = get(client, "/v1/meta").json()
    (aps,) = body["types"]
    assert aps["entities"] == 5
    assert [s["source"] for s in aps["sources"]] == ["aruba-central", "other"]
    assert aps["statuses"] == ["Down", "Up"]
    assert aps["dimensions"] == [{"key": "site_name", "distinct_values": 4}]
    assert {"event_type": "aps", "schema_version": "1"} in body["schemas"]


def test_dimension_values(client, fake):
    fake.responses.append([{"value": "HQ", "entities": 10}])
    body = get(client, "/v1/dimensions/values", event_type="aps", key="site_name", q="h").json()
    assert body == {"values": [{"value": "HQ", "entities": 10}]}
    assert fake.calls[0][1]["key"] == "site_name"


def test_queue_requires_admin(client, monkeypatch):
    assert get(client, "/v1/queue").status_code == 403
    monkeypatch.setattr(query.keystore, "authenticate", lambda raw: identity(role="admin"))
    import app.queue as queue_module

    monkeypatch.setattr(queue_module, "queue_stats", lambda: {"waiting": 1})
    assert get(client, "/v1/queue").json() == {"waiting": 1}


def test_health_and_metrics(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/metrics").status_code == 200
