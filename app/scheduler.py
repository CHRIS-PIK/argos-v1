from __future__ import annotations
import logging
import os
import time
from app.collectors.aps import collect as collect_aps
from app.collectors.clients import collect as collect_clients
from app.collectors.switches import collect as collect_switches
from app.collectors.radios import collect as collect_radios
from app.collectors.alerts import collect as collect_alerts
from app.collectors.licenses import collect as collect_licenses
from app.collectors.insights import collect as collect_insights
from app.retention import cleanup

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")

COLLECTORS = (
    ("aps", collect_aps),
    ("clients", collect_clients),
    ("switches", collect_switches),
    ("radios", collect_radios),
    ("alerts", collect_alerts),
    ("licenses", collect_licenses),
    ("insights", collect_insights),
)


def run_cycle() -> None:
    for name, fn in COLLECTORS:
        try:
            logging.info("starting collector=%s", name)
            fn()
            logging.info("finished collector=%s", name)
        except Exception:
            logging.exception("collector failed=%s", name)
    cleanup()


if __name__ == "__main__":
    while True:
        started = time.monotonic()
        run_cycle()
        elapsed = time.monotonic() - started
        time.sleep(max(10, 600 - elapsed))
