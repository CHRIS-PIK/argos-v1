from __future__ import annotations

import os
import threading
from typing import Any

_client: Any | None = None
_lock = threading.Lock()


def get_client():
    """Cliente ClickHouse compartilhado. Sem session id para permitir consultas concorrentes."""
    global _client
    with _lock:
        if _client is None:
            import clickhouse_connect

            _client = clickhouse_connect.get_client(
                host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
                username=os.getenv("CLICKHOUSE_QUERY_USER", os.getenv("CLICKHOUSE_USER", "default")),
                password=os.getenv("CLICKHOUSE_QUERY_PASSWORD", os.getenv("CLICKHOUSE_PASSWORD", "")),
                database=os.getenv("CLICKHOUSE_DATABASE", "argos"),
                autogenerate_session_id=False,
                settings={"max_execution_time": int(os.getenv("QUERY_MAX_SECONDS", "30"))},
            )
        return _client


def rows(sql: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    result = get_client().query(sql, parameters=parameters)
    return list(result.named_results())
