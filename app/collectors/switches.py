from app.api import ArubaClient
from app.processors import process_switches
from app.runlog import RunLog
from app.utils import utc_now


def collect() -> None:
    endpoint = "network-monitoring/v1/switches"
    client = ArubaClient()
    collected_at = utc_now()
    with RunLog("switches") as run:
        for items in client.pages(endpoint):
            run.pages += 1
            run.received += len(items)
            run.written += process_switches(items, collected_at)
