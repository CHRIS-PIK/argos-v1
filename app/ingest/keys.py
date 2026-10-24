from __future__ import annotations

import argparse
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from app.queue import get_redis

CACHE_TTL_SECONDS = 30
KEY_PREFIX = "argos:keys:"
INDEX = "argos:keys:index"


@dataclass(frozen=True)
class CollectorIdentity:
    key_id: str
    name: str
    tenant_id: str
    allowed_event_types: frozenset[str]

    def can_send(self, event_type: str) -> bool:
        return "*" in self.allowed_event_types or event_type in self.allowed_event_types


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class KeyStore:
    """Resolve API keys para identidades de coletor, com cache curto para não ir ao Redis a cada request."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, CollectorIdentity | None]] = {}

    def authenticate(self, raw_key: str) -> CollectorIdentity | None:
        key_hash = hash_key(raw_key)
        cached = self._cache.get(key_hash)
        now = time.monotonic()
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

        identity = self._lookup(key_hash)
        self._cache[key_hash] = (now, identity)
        return identity

    @staticmethod
    def _lookup(key_hash: str) -> CollectorIdentity | None:
        client = get_redis()
        record = client.hgetall(KEY_PREFIX + key_hash)
        if not record or record.get("enabled") != "1":
            return None
        client.hset(KEY_PREFIX + key_hash, "last_used_at", datetime.now(timezone.utc).isoformat())
        allowed = frozenset(
            part.strip() for part in record.get("allowed_event_types", "*").split(",") if part.strip()
        )
        return CollectorIdentity(
            key_id=key_hash[:12],
            name=record["name"],
            tenant_id=record.get("tenant_id", "default"),
            allowed_event_types=allowed,
        )


def create_key(name: str, tenant_id: str, allowed_event_types: str) -> str:
    raw_key = "argos_" + secrets.token_urlsafe(32)
    key_hash = hash_key(raw_key)
    client = get_redis()
    client.hset(KEY_PREFIX + key_hash, mapping={
        "name": name,
        "tenant_id": tenant_id,
        "allowed_event_types": allowed_event_types,
        "enabled": "1",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    client.sadd(INDEX, key_hash)
    return raw_key


def revoke_key(name: str) -> int:
    client = get_redis()
    revoked = 0
    for key_hash in client.smembers(INDEX):
        record_key = KEY_PREFIX + key_hash
        if client.hget(record_key, "name") == name and client.hget(record_key, "enabled") == "1":
            client.hset(record_key, "enabled", "0")
            revoked += 1
    return revoked


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerencia API keys de coletores.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Cria uma chave. O valor é exibido uma única vez.")
    create.add_argument("--name", required=True)
    create.add_argument("--tenant", default="default")
    create.add_argument("--event-types", default="*", help="Lista separada por vírgula ou '*'.")

    revoke = sub.add_parser("revoke", help="Desativa as chaves com esse nome.")
    revoke.add_argument("--name", required=True)

    args = parser.parse_args()
    if args.command == "create":
        print(create_key(args.name, args.tenant, args.event_types))
    else:
        print(f"revoked={revoke_key(args.name)}")


if __name__ == "__main__":
    main()
