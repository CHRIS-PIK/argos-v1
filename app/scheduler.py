from __future__ import annotations
import logging
import os
import time
from app.collectors.aps import collect as collect_aps
from app.collectors.clients import collect as collect_clients
from app.retention import cleanup

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")

def run_cycle() -> None:
    for name, fn in (("aps", collect_aps), ("clients", collect_clients)):
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
