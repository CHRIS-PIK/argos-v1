"""Paginação do cliente Aruba: a última página de uma paginação por cursor não pode gerar
um pedido extra por offset (que a API recusa com 400)."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

ARUBA = Path(__file__).resolve().parents[1] / "collectors" / "aruba"
sys.path.insert(0, str(ARUBA))

for name, value in {
    "ARUBA_BASE_URL": "https://aruba.test",
    "ARUBA_AUTH_URL": "https://aruba.test/token",
    "ARUBA_CLIENT_ID": "id",
    "ARUBA_CLIENT_SECRET": "secret",
    "ARGOS_INGEST_URL": "http://ingest:8000",
    "ARGOS_API_KEY": "argos_test",
}.items():
    os.environ.setdefault(name, value)

sys.modules.setdefault("fcntl", types.ModuleType("fcntl"))  # auth.py usa fcntl (só Linux)

import aruba_client  # noqa: E402


class FakeResponse:
    status_code = 200

    def __init__(self, body: dict) -> None:
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        pass


@pytest.fixture()
def client(monkeypatch):
    class FakeTokens:
        def get_access_token(self) -> str:
            return "token"

    monkeypatch.setattr(aruba_client, "TokenManager", FakeTokens)
    return aruba_client.ArubaClient()


def serve(client, pages: list[dict]):
    """Responde em ordem e registra os parâmetros de cada pedido."""
    requests_made: list[dict] = []
    queue = list(pages)

    def fake_get(url, headers, params):
        requests_made.append(dict(params))
        if not queue:
            raise AssertionError(f"pedido inesperado: {params}")
        return FakeResponse(queue.pop(0))

    client.get = fake_get
    return requests_made


def items(n: int) -> list[dict]:
    return [{"id": str(i)} for i in range(n)]


def test_cursor_pagination_stops_after_the_last_page(client):
    made = serve(client, [
        {"items": items(100), "next": "c1", "total": 250},
        {"items": items(100), "next": "c2", "total": 250},
        {"items": items(50), "total": 250},  # sem `next`: fim
    ])
    pages = list(client.pages("network-monitoring/v1/aps"))
    assert [len(p) for p in pages] == [100, 100, 50]
    assert len(made) == 3
    assert [m.get("next") for m in made] == [None, "c1", "c2"]
    assert all("offset" not in m for m in made[1:])


def test_offset_pagination_without_cursor_still_works(client):
    made = serve(client, [
        {"items": items(100), "total": 250},
        {"items": items(100), "total": 250},
        {"items": items(50), "total": 250},
    ])
    pages = list(client.pages("x"))
    assert [len(p) for p in pages] == [100, 100, 50]
    assert [m.get("offset") for m in made] == [None, 100, 200]


def test_single_page_makes_one_request(client):
    made = serve(client, [{"items": items(12), "total": 12}])
    assert [len(p) for p in client.pages("x")] == [12]
    assert len(made) == 1


def test_repeated_cursor_is_not_followed_twice(client):
    made = serve(client, [
        {"items": items(10), "next": "c1", "total": 99},
        {"items": items(10), "next": "c1", "total": 99},
    ])
    assert [len(p) for p in client.pages("x")] == [10, 10]
    assert len(made) == 2
