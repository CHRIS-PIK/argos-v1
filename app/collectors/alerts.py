from app.api import ArubaClient
from app.processors import process_alerts
from app.runlog import RunLog
from app.utils import utc_now


def collect() -> None:
    endpoint = "network-notifications/v1/alerts"
    client = ArubaClient()
    collected_at = utc_now()
    with RunLog("alerts") as run:
        for items in client.pages(endpoint):
            run.pages += 1
            run.received += len(items)
            run.written += process_alerts(items, collected_at)
