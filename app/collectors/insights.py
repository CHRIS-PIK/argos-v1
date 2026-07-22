from __future__ import annotations
import json
from app.api import ArubaClient
from app.db import connection
from app.runlog import RunLog
from app.utils import bucket_10m, first, utc_now

SQL = """
INSERT INTO insight_current (entity_id, scope_type, scope_id, collected_at, updated_at, raw_json)
VALUES (%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE scope_type=VALUES(scope_type), scope_id=VALUES(scope_id), collected_at=VALUES(collected_at), updated_at=VALUES(updated_at), raw_json=VALUES(raw_json)
"""


def _store(client: ArubaClient, endpoint: str, scope_type: str, scope_id: str, run) -> None:
    collected_at = bucket_10m()
    for items in client.pages(endpoint):
        run.pages += 1
        now = utc_now()
        rows = []
        for item in items:
            item_id = str(first(item, "id", "insightId", "uuid", default=""))
            if item_id:
                rows.append((f"{scope_type}:{scope_id}:{item_id}", scope_type, scope_id, collected_at, now, json.dumps(item, ensure_ascii=False)))
        run.received += len(rows)
        if rows:
            with connection() as cnx:
                cnx.cursor().executemany(SQL, rows)
            run.written += len(rows)


def collect() -> None:
    client = ArubaClient()
    with RunLog("insights") as run:
        _store(client, "aiops/v2/insights/global/list", "global", "global", run)
        with connection() as cnx:
            cur = cnx.cursor()
            cur.execute("SELECT DISTINCT site_id FROM ap_current WHERE site_id IS NOT NULL AND site_id <> ''")
            site_ids = [str(row[0]) for row in cur.fetchall()]
        for site_id in site_ids:
            _store(client, f"aiops/v2/insights/site/{site_id}/list", "site", site_id, run)
