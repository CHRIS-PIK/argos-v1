from __future__ import annotations

import argparse
import hashlib
import secrets
import time
from dataclasses import dataclass

from app.db import connection

CACHE_TTL_SECONDS = 30


@dataclass(frozen=True)
class CollectorIdentity:
    key_id: int
    name: str
    tenant_id: str
    allowed_event_types: frozenset[str]

    def can_send(self, event_type: str) -> bool:
        return "*" in self.allowed_event_types or event_type in self.allowed_event_types


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class KeyStore:
    """Resolve API keys para identidades de coletor, com cache curto para não ir ao banco a cada request."""

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
        with connection() as cnx:
            cur = cnx.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, name, tenant_id, allowed_event_types
                  FROM collector_keys
                 WHERE key_hash=%s AND enabled=1
                """,
                (key_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            cur.execute(
                "UPDATE collector_keys SET last_used_at=UTC_TIMESTAMP(6) WHERE id=%s",
                (row["id"],),
            )
        allowed = frozenset(
            part.strip() for part in str(row["allowed_event_types"]).split(",") if part.strip()
        )
        return CollectorIdentity(
            key_id=int(row["id"]),
            name=str(row["name"]),
            tenant_id=str(row["tenant_id"]),
            allowed_event_types=allowed,
        )


def create_key(name: str, tenant_id: str, allowed_event_types: str) -> str:
    raw_key = "argos_" + secrets.token_urlsafe(32)
    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute(
            """
            INSERT INTO collector_keys (name, key_hash, tenant_id, allowed_event_types)
            VALUES (%s,%s,%s,%s)
            """,
            (name, hash_key(raw_key), tenant_id, allowed_event_types),
        )
    return raw_key


def revoke_key(name: str) -> int:
    with connection() as cnx:
        cur = cnx.cursor()
        cur.execute("UPDATE collector_keys SET enabled=0 WHERE name=%s", (name,))
        return cur.rowcount


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
