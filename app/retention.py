from __future__ import annotations
from app.config import settings
from app.db import connection

def cleanup() -> None:
    with connection() as cnx:
        cur = cnx.cursor()
        for table in ("ap_metrics_10m", "client_summary_10m"):
            cur.execute(f"DELETE FROM {table} WHERE collected_at < UTC_TIMESTAMP() - INTERVAL %s DAY", (settings.retention_days,))
        cur.execute("DELETE FROM ingestion_runs WHERE started_at < UTC_TIMESTAMP() - INTERVAL 180 DAY")
