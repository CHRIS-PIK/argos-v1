from __future__ import annotations
import json
from app.api import ArubaClient
from app.db import connection
from app.runlog import RunLog
from app.utils import bucket_10m, first, parse_dt, utc_now

CURRENT_SQL = """
INSERT INTO ap_current
(ap_id,serial_number,device_name,mac_address,site_id,site_name,device_group_name,model,status,firmware_version,ipv4,last_seen_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE serial_number=VALUES(serial_number),device_name=VALUES(device_name),mac_address=VALUES(mac_address),
site_id=VALUES(site_id),site_name=VALUES(site_name),device_group_name=VALUES(device_group_name),model=VALUES(model),
status=VALUES(status),firmware_version=VALUES(firmware_version),ipv4=VALUES(ipv4),last_seen_at=VALUES(last_seen_at),
updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
"""
METRIC_SQL = """
INSERT INTO ap_metrics_10m
(ap_id,collected_at,site_id,cpu_utilization,memory_utilization,power_consumption,wlan_count,client_count,uptime_ms,status)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE cpu_utilization=VALUES(cpu_utilization),memory_utilization=VALUES(memory_utilization),
power_consumption=VALUES(power_consumption),wlan_count=VALUES(wlan_count),client_count=VALUES(client_count),
uptime_ms=VALUES(uptime_ms),status=VALUES(status)
"""

def collect() -> None:
    client = ArubaClient()
    collected_at = bucket_10m()
    with RunLog("aps") as run:
        for items in client.pages("network-monitoring/v1/aps"):
            run.pages += 1
            filtered = [x for x in items if x.get("deviceGroupName") != "Onboarding-AP" and x.get("siteName") != "Onboarding"]
            run.received += len(filtered)
            now = utc_now()
            current_rows, metric_rows = [], []
            for ap in filtered:
                ap_id = str(first(ap, "id", "serialNumber", "macAddress", default=""))
                if not ap_id:
                    continue
                current_rows.append((ap_id, ap.get("serialNumber"), ap.get("deviceName"), ap.get("macAddress"), ap.get("siteId"), ap.get("siteName"), ap.get("deviceGroupName"), ap.get("model"), ap.get("status"), ap.get("firmwareVersion"), ap.get("ipv4"), parse_dt(ap.get("lastSeenAt")), now, json.dumps(ap, ensure_ascii=False)))
                metric_rows.append((ap_id, collected_at, ap.get("siteId"), ap.get("cpuUtilization"), ap.get("memoryUtilization"), ap.get("powerConsumption"), ap.get("wlanCount"), ap.get("clientCount"), ap.get("uptimeInMillis"), ap.get("status")))
            with connection() as cnx:
                cur = cnx.cursor()
                if current_rows: cur.executemany(CURRENT_SQL, current_rows)
                if metric_rows: cur.executemany(METRIC_SQL, metric_rows)
            run.written += len(current_rows) + len(metric_rows)
