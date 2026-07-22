from __future__ import annotations
import json
from collections import Counter
from app.api import ArubaClient
from app.db import connection
from app.runlog import RunLog
from app.utils import bucket_10m, first, parse_dt, utc_now

CURRENT_SQL = """
INSERT INTO client_current
(client_id,mac_address,client_name,username,ip_address,site_id,site_name,device_id,device_name,connection_type,wireless_band,wlan_name,status,first_seen_at,last_seen_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE mac_address=VALUES(mac_address),client_name=VALUES(client_name),username=VALUES(username),ip_address=VALUES(ip_address),
site_id=VALUES(site_id),site_name=VALUES(site_name),device_id=VALUES(device_id),device_name=VALUES(device_name),
connection_type=VALUES(connection_type),wireless_band=VALUES(wireless_band),wlan_name=VALUES(wlan_name),status=VALUES(status),
first_seen_at=COALESCE(first_seen_at,VALUES(first_seen_at)),last_seen_at=VALUES(last_seen_at),updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
"""
SUMMARY_SQL = """
INSERT INTO client_summary_10m
(collected_at,site_id,site_name,device_id,device_name,connection_type,wireless_band,wlan_name,connected_clients)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE site_name=VALUES(site_name),device_name=VALUES(device_name),connected_clients=VALUES(connected_clients)
"""

def collect() -> None:
    client = ArubaClient()
    collected_at = bucket_10m()
    summary = Counter()
    names = {}
    with RunLog("clients") as run:
        for items in client.pages("network-monitoring/v1/clients"):
            run.pages += 1
            filtered = [x for x in items if x.get("siteName") != "Onboarding"]
            run.received += len(filtered)
            now = utc_now()
            rows = []
            for c in filtered:
                client_id = str(first(c, "id", "clientId", "macAddress", "mac", default=""))
                if not client_id:
                    continue
                site_id = str(first(c, "siteId", default="") or "")
                device_id = str(first(c, "deviceId", "apId", "switchId", default="") or "")
                conn_type = str(first(c, "clientConnectionType", "connectionType", "type", default="") or "")
                band = str(first(c, "wirelessBand", "band", default="") or "")
                wlan = str(first(c, "wlanName", "ssid", default="") or "")
                rows.append((client_id, first(c,"macAddress","mac"), c.get("clientName"), first(c,"username","userName"), first(c,"ipAddress","ipv4"), site_id, c.get("siteName"), device_id, first(c,"deviceName","apName","switchName"), conn_type, band, wlan, c.get("status"), parse_dt(first(c,"firstSeenAt","connectedAt")), parse_dt(first(c,"lastSeenAt","updatedAt")), now, json.dumps(c, ensure_ascii=False)))
                key = (site_id, device_id, conn_type, band, wlan)
                summary[key] += 1
                names[key] = (c.get("siteName"), first(c,"deviceName","apName","switchName"))
            with connection() as cnx:
                cur = cnx.cursor()
                if rows: cur.executemany(CURRENT_SQL, rows)
            run.written += len(rows)
        summary_rows = [(collected_at, *key[:1], names[key][0], key[1], names[key][1], key[2], key[3], key[4], count) for key, count in summary.items()]
        with connection() as cnx:
            cur = cnx.cursor()
            if summary_rows: cur.executemany(SUMMARY_SQL, summary_rows)
        run.written += len(summary_rows)
