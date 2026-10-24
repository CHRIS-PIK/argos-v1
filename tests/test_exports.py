from __future__ import annotations

import csv
import io
import json
import os
import sys
import types
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path

import fakeredis
import pytest

os.environ["SCHEMAS_DIR"] = str(Path(__file__).resolve().parents[1] / "collectors" / "aruba" / "schemas")

runtime_stub = types.ModuleType("app.observability.runtime")
runtime_stub.configure_observability = lambda service_name: None
sys.modules["app.observability.runtime"] = runtime_stub

from fastapi.testclient import TestClient  # noqa: E402

from app import queue  # noqa: E402
from app.ingest.keys import CollectorIdentity  # noqa: E402
from app.query import db, exports, main as query  # noqa: E402

KEY = "reader-key"
T = datetime(2026, 10, 24, 19, 40, tzinfo=timezone.utc)


def identity(tenant="acme") -> CollectorIdentity:
    return CollectorIdentity(
        key_id="k", name="t", tenant_id=tenant, allowed_event_types=frozenset({"*"}), role="reader"
    )


def make_rows(n: int) -> list[dict]:
    return [
        {
            "tenant_id": "acme", "event_type": "aps", "source": "aruba-central",
            "schema_version": "1", "entity_id": f"ap-{i:03d}", "name": f"AP {i}", "status": "Up",
            "dimensions": {"site_name": "HQ", "floor": str(i % 3)}, "bucket_at": T,
            "collected_at": T, "ingested_at": T, "batch_id": "b",
            "payload": json.dumps({"id": f"ap-{i:03d}", "cpu": i}),
        }
        for i in range(n)
    ]


class FakeDb:
    def __init__(self, rows: list[dict]) -> None:
        self.all = rows
        self.queries: list[str] = []

    def rows(self, sql, parameters):
        self.queries.append(sql)
        if "count()" in sql:
            return [{"total": len(self.all)}]
        start = 0
        if "c2" in parameters:  # keyset: depois da entidade do cursor
            ids = [r["entity_id"] for r in self.all]
            start = ids.index(parameters["c2"] if "(event_type, source, entity_id) >" in sql else parameters["c3"]) + 1
        return self.all[start:start + parameters["limit"]]


class SyncExecutor:
    def submit(self, fn, *args):
        future: Future = Future()
        future.set_result(fn(*args))
        return future


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    server = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(queue, "_client", server)
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    monkeypatch.setattr(exports, "executor", SyncExecutor())
    monkeypatch.setattr(exports, "BATCH", 2)
    monkeypatch.setattr(query.keystore, "authenticate",
                        lambda raw: identity() if raw == KEY else None)


@pytest.fixture()
def client():
    return TestClient(query.app)


def use_rows(monkeypatch, n: int) -> FakeDb:
    fake = FakeDb(make_rows(n))
    monkeypatch.setattr(db, "rows", fake.rows)
    return fake


H = {"X-API-Key": KEY}


def test_direct_csv_streams_all_rows_across_batches(client, monkeypatch):
    fake = use_rows(monkeypatch, 5)
    response = client.get("/v1/export", params={"dataset": "entities"}, headers=H)
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="argos-entities-')
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert [r["entity_id"] for r in rows] == [f"ap-{i:03d}" for i in range(5)]
    assert json.loads(rows[0]["dimensions"]) == {"site_name": "HQ", "floor": "0"}
    assert rows[0]["collected_at"] == "2026-10-24T19:40:00Z"
    assert "payload" not in rows[0]
    assert sum("count()" not in q for q in fake.queries) == 3  # lotes de 2: 2 + 2 + 1


def test_direct_expands_dimension_columns_and_payload(client, monkeypatch):
    use_rows(monkeypatch, 2)
    response = client.get(
        "/v1/export",
        params={"dataset": "entities", "dimension_columns": "site_name,floor", "include_payload": "true"},
        headers=H,
    )
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[1]["dim.site_name"] == "HQ" and rows[1]["dim.floor"] == "1"
    assert "dimensions" not in rows[1]
    assert json.loads(rows[1]["payload"])["cpu"] == 1


def test_direct_jsonl(client, monkeypatch):
    use_rows(monkeypatch, 2)
    response = client.get("/v1/export", params={"dataset": "entities", "format": "jsonl"}, headers=H)
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [line["entity_id"] for line in lines] == ["ap-000", "ap-001"]


def test_direct_rejects_large_results(client, monkeypatch):
    use_rows(monkeypatch, 3)
    monkeypatch.setenv("EXPORT_DIRECT_LIMIT", "2")
    response = client.get("/v1/export", params={"dataset": "entities"}, headers=H)
    assert response.status_code == 413
    assert "POST /v1/exports" in response.json()["detail"]


def test_direct_requires_reader(client, monkeypatch):
    use_rows(monkeypatch, 1)
    assert client.get("/v1/export", params={"dataset": "entities"}).status_code == 401


def test_direct_only_allows_text_formats(client, monkeypatch):
    use_rows(monkeypatch, 1)
    response = client.get("/v1/export", params={"dataset": "entities", "format": "xlsx"}, headers=H)
    assert response.status_code == 422


def run_job(client, body):
    created = client.post("/v1/exports", json=body, headers=H)
    assert created.status_code == 202
    return created.json()["id"]


def test_job_csv_lifecycle(client, monkeypatch):
    use_rows(monkeypatch, 5)
    job_id = run_job(client, {"dataset": "entities", "format": "csv"})
    status = client.get(f"/v1/exports/{job_id}", headers=H).json()
    assert status["status"] == "done" and status["rows"] == 5 and status["truncated"] is False
    assert status["download_url"] == f"/v1/exports/{job_id}/download"
    assert "tenant_id" not in status and "file" not in status

    download = client.get(status["download_url"], headers=H)
    assert download.status_code == 200
    assert download.content.startswith(b"\xef\xbb\xbf")  # BOM para o Excel abrir UTF-8
    rows = list(csv.DictReader(io.StringIO(download.content.decode("utf-8-sig"))))
    assert len(rows) == 5


def test_job_is_truncated_at_max_rows(client, monkeypatch):
    use_rows(monkeypatch, 5)
    monkeypatch.setenv("EXPORT_MAX_ROWS", "3")
    job_id = run_job(client, {"dataset": "entities", "format": "jsonl"})
    status = client.get(f"/v1/exports/{job_id}", headers=H).json()
    assert (status["rows"], status["total"], status["truncated"]) == (3, 5, True)


def test_job_xlsx(client, monkeypatch):
    from openpyxl import load_workbook

    use_rows(monkeypatch, 3)
    job_id = run_job(client, {"dataset": "entities", "format": "xlsx", "dimension_columns": ["site_name"]})
    download = client.get(f"/v1/exports/{job_id}/download", headers=H)
    sheet = load_workbook(io.BytesIO(download.content)).active
    values = list(sheet.values)
    assert values[0][4] == "entity_id" and "dim.site_name" in values[0]
    assert len(values) == 4 and values[1][4] == "ap-000"


def test_job_parquet(client, monkeypatch):
    import pyarrow.parquet as pq

    use_rows(monkeypatch, 3)
    job_id = run_job(client, {"dataset": "entities", "format": "parquet"})
    download = client.get(f"/v1/exports/{job_id}/download", headers=H)
    table = pq.read_table(io.BytesIO(download.content))
    assert table.num_rows == 3
    assert str(table.schema.field("collected_at").type) == "timestamp[ms, tz=UTC]"
    assert table.column("entity_id").to_pylist() == ["ap-000", "ap-001", "ap-002"]


def test_failed_job_reports_error_and_download_conflicts(client, monkeypatch):
    def boom(sql, parameters):
        raise RuntimeError("clickhouse down")

    monkeypatch.setattr(db, "rows", boom)
    job_id = run_job(client, {"dataset": "entities"})
    status = client.get(f"/v1/exports/{job_id}", headers=H).json()
    assert status["status"] == "failed" and "clickhouse down" in status["error"]
    assert client.get(f"/v1/exports/{job_id}/download", headers=H).status_code == 409


def test_jobs_are_isolated_by_tenant(client, monkeypatch):
    use_rows(monkeypatch, 1)
    job_id = run_job(client, {"dataset": "entities"})
    monkeypatch.setattr(query.keystore, "authenticate", lambda raw: identity(tenant="other"))
    assert client.get(f"/v1/exports/{job_id}", headers=H).status_code == 404
    assert client.get(f"/v1/exports/{job_id}/download", headers=H).status_code == 404


def test_events_export_requires_valid_window(client, monkeypatch):
    use_rows(monkeypatch, 1)
    body = {"dataset": "events", "from": "2026-10-24T10:00:00Z", "to": "2026-10-24T09:00:00Z"}
    assert client.post("/v1/exports", json=body, headers=H).status_code == 422


def test_invalid_export_requests_are_rejected(client, monkeypatch):
    use_rows(monkeypatch, 1)
    assert client.post("/v1/exports", json={"dataset": "nope"}, headers=H).status_code == 422
    bad = {"dataset": "entities", "dimension_columns": ["bad key"]}
    assert client.post("/v1/exports", json=bad, headers=H).status_code == 422


def test_unknown_job_is_404(client):
    assert client.get("/v1/exports/deadbeef", headers=H).status_code == 404
