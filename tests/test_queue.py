from __future__ import annotations

import sys
import types
from datetime import datetime

import fakeredis
import pytest

runtime_stub = types.ModuleType("app.observability.runtime")
runtime_stub.configure_observability = lambda service_name: None
sys.modules["app.observability.runtime"] = runtime_stub

from app import queue  # noqa: E402
from app import worker  # noqa: E402
from app.ingest import keys  # noqa: E402


@pytest.fixture(autouse=True)
def redis_server(monkeypatch):
    server = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(queue, "_client", server)
    queue.ensure_group()
    return server


def enqueue(batch_id="b1", **kwargs) -> bool:
    args = dict(
        tenant_id="acme", source="src", event_type="generic", schema_version="1",
        batch_id=batch_id, page_number=1, collected_at=datetime(2026, 10, 24, 19, 47),
        bucket_at=datetime(2026, 10, 24, 19, 40), items=[{"id": "1"}],
    )
    args.update(kwargs)
    return queue.enqueue_event(**args)


def test_enqueue_dedups_by_batch_id():
    assert enqueue() is True
    assert enqueue() is False
    assert enqueue(batch_id="b2") is True


def test_enqueue_failure_releases_dedup_key(redis_server, monkeypatch):
    original = redis_server.xadd

    def boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(redis_server, "xadd", boom)
    with pytest.raises(RuntimeError):
        enqueue()
    monkeypatch.setattr(redis_server, "xadd", original)
    assert enqueue() is True


def test_read_ack_removes_message(redis_server):
    enqueue()
    (message,) = queue.read_new(10, 10)
    assert message["collector_name"] == "generic"
    assert message["source"] == "src"
    assert message["tenant_id"] == "acme"
    assert message["attempts"] == 1
    queue.ack(message["id"])
    assert redis_server.xlen(queue.STREAM) == 0
    assert queue.read_new(10, 10) == []


def test_unacked_message_is_reclaimed_with_attempt_count():
    enqueue()
    (first,) = queue.read_new(10, 10)
    (again,) = queue.claim_stale(0, 10)
    assert again["id"] == first["id"]
    assert again["attempts"] == 2


def test_dead_letter_moves_message_and_clears_pending(redis_server):
    enqueue()
    (message,) = queue.read_new(10, 10)
    queue.dead_letter(message, "boom")
    assert redis_server.xlen(queue.STREAM) == 0
    ((_id, fields),) = redis_server.xrange(queue.DEAD_STREAM)
    assert fields["error"] == "boom"
    assert fields["event_type"] == "generic"
    assert queue.claim_stale(0, 10) == []


def test_api_keys_roundtrip():
    raw = keys.create_key("collector-a", "acme", "aps,clients")
    identity = keys.KeyStore().authenticate(raw)
    assert identity.tenant_id == "acme"
    assert identity.can_send("aps") and not identity.can_send("alerts")
    assert keys.KeyStore().authenticate("nope") is None
    assert keys.revoke_key("collector-a") == 1
    assert keys.KeyStore().authenticate(raw) is None


class FakeSink:
    def __init__(self, fail=False):
        self.fail = fail
        self.written = []

    def write(self, message, items):
        if self.fail:
            raise RuntimeError("clickhouse down")
        self.written.append((message["id"], items))
        return len(items)


def test_worker_acks_on_success(redis_server):
    enqueue()
    (message,) = queue.read_new(10, 10)
    sink = FakeSink()
    worker.handle_message(message, sink)
    assert sink.written == [(message["id"], [{"id": "1"}])]
    assert redis_server.xlen(queue.STREAM) == 0


def test_worker_retries_then_dead_letters(redis_server, monkeypatch):
    monkeypatch.setenv("QUEUE_MAX_ATTEMPTS", "2")
    enqueue()
    (message,) = queue.read_new(10, 10)
    worker.handle_message(message, FakeSink(fail=True))
    assert redis_server.xlen(queue.STREAM) == 1
    assert redis_server.xlen(queue.DEAD_STREAM) == 0

    (retry,) = queue.claim_stale(0, 10)
    worker.handle_message(retry, FakeSink(fail=True))
    assert redis_server.xlen(queue.STREAM) == 0
    assert redis_server.xlen(queue.DEAD_STREAM) == 1
