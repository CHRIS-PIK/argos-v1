from __future__ import annotations
from app.db import connection
from app.utils import utc_now

class RunLog:
    def __init__(self, collector: str):
        self.collector = collector
        self.run_id = None
        self.pages = 0
        self.received = 0
        self.written = 0

    def __enter__(self):
        with connection() as cnx:
            cur = cnx.cursor()
            cur.execute("INSERT INTO ingestion_runs (collector_name, started_at, status) VALUES (%s,%s,'RUNNING')", (self.collector, utc_now()))
            self.run_id = cur.lastrowid
        return self

    def success(self):
        with connection() as cnx:
            cur = cnx.cursor()
            cur.execute("UPDATE ingestion_runs SET finished_at=%s,status='SUCCESS',pages_processed=%s,records_received=%s,records_written=%s WHERE id=%s", (utc_now(), self.pages, self.received, self.written, self.run_id))

    def fail(self, exc: Exception):
        with connection() as cnx:
            cur = cnx.cursor()
            cur.execute("UPDATE ingestion_runs SET finished_at=%s,status='FAILED',pages_processed=%s,records_received=%s,records_written=%s,error_message=%s WHERE id=%s", (utc_now(), self.pages, self.received, self.written, str(exc)[:65000], self.run_id))

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            self.success()
            return False
        self.fail(exc)
        return False
