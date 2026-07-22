from __future__ import annotations
import json
from collections.abc import Callable
from app.api import ArubaClient
from app.db import connection
from app.runlog import RunLog
from app.utils import bucket_10m, first, utc_now


def collect_current(
    collector_name: str,
    endpoint: str,
    table: str,
    id_fields: tuple[str, ...],
    params: dict | None = None,
    row_filter: Callable[[dict], bool] | None = None,
) -> None:
    sql = f"""
    INSERT INTO {table} (entity_id, collected_at, updated_at, raw_json)
    VALUES (%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE collected_at=VALUES(collected_at), updated_at=VALUES(updated_at), raw_json=VALUES(raw_json)
    """
    client = ArubaClient()
    collected_at = bucket_10m()
    with RunLog(collector_name) as run:
        for items in client.pages(endpoint, params=params):
            run.pages += 1
            rows = []
            now = utc_now()
            for item in items:
                if row_filter and not row_filter(item):
                    continue
                entity_id = str(first(item, *id_fields, default=""))
                if not entity_id:
                    continue
                rows.append((entity_id, collected_at, now, json.dumps(item, ensure_ascii=False)))
            run.received += len(rows)
            if rows:
                with connection() as cnx:
                    cnx.cursor().executemany(sql, rows)
                run.written += len(rows)
