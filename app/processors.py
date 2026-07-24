from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from app.db import connection
from app.utils import first, parse_dt, utc_now

RAW_CURRENT_SQL = '''
INSERT INTO raw_entity_current
(collector_name, entity_id, site_id, site_name, entity_name, status,
 source_collected_at, updated_at, raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 site_id=VALUES(site_id), site_name=VALUES(site_name),
 entity_name=VALUES(entity_name), status=VALUES(status),
 source_collected_at=VALUES(source_collected_at),
 updated_at=VALUES(updated_at), raw_json=VALUES(raw_json)
'''

RAW_SNAPSHOT_SQL = '''
INSERT INTO raw_entity_snapshot_10m
(collector_name, entity_id, collected_at, site_id, status, raw_json)
VALUES (%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 site_id=VALUES(site_id), status=VALUES(status), raw_json=VALUES(raw_json)
'''

AP_CURRENT_SQL = '''
INSERT INTO ap_current
(ap_id,serial_number,device_name,mac_address,site_id,site_name,device_group_name,
 model,status,firmware_version,ipv4,last_seen_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 serial_number=VALUES(serial_number),device_name=VALUES(device_name),
 mac_address=VALUES(mac_address),site_id=VALUES(site_id),site_name=VALUES(site_name),
 device_group_name=VALUES(device_group_name),model=VALUES(model),
 status=VALUES(status),firmware_version=VALUES(firmware_version),
 ipv4=VALUES(ipv4),last_seen_at=VALUES(last_seen_at),
 updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
'''

AP_METRIC_SQL = '''
INSERT INTO ap_metrics_10m
(ap_id,collected_at,site_id,cpu_utilization,memory_utilization,power_consumption,
 wlan_count,client_count,uptime_ms,status)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 cpu_utilization=VALUES(cpu_utilization), memory_utilization=VALUES(memory_utilization),
 power_consumption=VALUES(power_consumption), wlan_count=VALUES(wlan_count),
 client_count=VALUES(client_count), uptime_ms=VALUES(uptime_ms), status=VALUES(status)
'''

CLIENT_CURRENT_SQL = '''
INSERT INTO client_current
(client_id,mac_address,client_name,username,host_name,status,ip_address,ipv6,
 site_id,site_name,device_id,device_name,connected_device_type,connected_device_serial,
 connected_to,port,role,connection_type,vlan_id,vlan_name,tunnel_type,tunnel_id,
 wlan_name,wireless_band,wireless_channel,bssid,radio_mac_address,wireless_security,
 key_management,authentication_type,client_capabilities,phy_type,snr,mlo_oper_mode,
 client_manufacturer,client_function,client_vendor,client_operating_system,
 client_category,client_tags,connected_at,first_seen_at,last_seen_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 mac_address=VALUES(mac_address),client_name=VALUES(client_name),username=VALUES(username),
 host_name=VALUES(host_name),status=VALUES(status),ip_address=VALUES(ip_address),
 ipv6=VALUES(ipv6),site_id=VALUES(site_id),site_name=VALUES(site_name),
 device_id=VALUES(device_id),device_name=VALUES(device_name),
 connected_device_type=VALUES(connected_device_type),
 connected_device_serial=VALUES(connected_device_serial),connected_to=VALUES(connected_to),
 port=VALUES(port),role=VALUES(role),connection_type=VALUES(connection_type),
 vlan_id=VALUES(vlan_id),vlan_name=VALUES(vlan_name),tunnel_type=VALUES(tunnel_type),
 tunnel_id=VALUES(tunnel_id),wlan_name=VALUES(wlan_name),
 wireless_band=VALUES(wireless_band),wireless_channel=VALUES(wireless_channel),
 bssid=VALUES(bssid),radio_mac_address=VALUES(radio_mac_address),
 wireless_security=VALUES(wireless_security),key_management=VALUES(key_management),
 authentication_type=VALUES(authentication_type),
 client_capabilities=VALUES(client_capabilities),phy_type=VALUES(phy_type),
 snr=VALUES(snr),mlo_oper_mode=VALUES(mlo_oper_mode),
 client_manufacturer=VALUES(client_manufacturer),client_function=VALUES(client_function),
 client_vendor=VALUES(client_vendor),client_operating_system=VALUES(client_operating_system),
 client_category=VALUES(client_category),client_tags=VALUES(client_tags),
 connected_at=VALUES(connected_at),first_seen_at=COALESCE(first_seen_at,VALUES(first_seen_at)),
 last_seen_at=VALUES(last_seen_at),updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
'''

CLIENT_SUMMARY_SQL = '''
INSERT INTO client_summary_10m
(collected_at,site_id,site_name,device_id,device_name,connection_type,
 wireless_band,wlan_name,connected_clients)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 site_name=VALUES(site_name), device_name=VALUES(device_name),
 connected_clients=VALUES(connected_clients)
'''

SPECIALIZED_RAW_TABLES = {
    "switches": "switch_current",
    "radios": "radio_current",
    "alerts": "alert_current",
}


def entity_id(item: dict[str, Any]) -> str:
    return str(first(item, "id", "serialNumber", "clientId", "macAddress", "mac",
                     "subscriptionId", "insightId", "alertId", default="") or "")


def process_raw(collector_name: str, items: list[dict[str, Any]], collected_at: datetime, bucket_at: datetime) -> int:
    now = utc_now()
    current_rows, snapshot_rows = [], []
    for item in items:
        item_id = entity_id(item)
        if not item_id:
            continue
        site_id = str(first(item, "siteId", default="") or "")
        site_name = first(item, "siteName")
        name = first(item, "deviceName", "name", "title", "subscriptionName", "insightName", "alertName")
        status = str(first(item, "status", "state", "severity", default="") or "")
        raw = json.dumps(item, ensure_ascii=False)
        current_rows.append((collector_name, item_id, site_id, site_name, name, status, collected_at, now, raw))
        snapshot_rows.append((collector_name, item_id, bucket_at, site_id, status, raw))
    with connection() as cnx:
        cur = cnx.cursor()
        if current_rows:
            cur.executemany(RAW_CURRENT_SQL, current_rows)
        if snapshot_rows:
            cur.executemany(RAW_SNAPSHOT_SQL, snapshot_rows)
    return len(current_rows) + len(snapshot_rows)


def process_aps(items: list[dict[str, Any]], collected_at: datetime, bucket_at: datetime) -> int:
    now = utc_now()
    current_rows, metric_rows = [], []
    for ap in items:
        if ap.get("deviceGroupName") == "Onboarding-AP" or ap.get("siteName") == "Onboarding":
            continue
        ap_id = entity_id(ap)
        if not ap_id:
            continue
        raw = json.dumps(ap, ensure_ascii=False)
        current_rows.append((ap_id, ap.get("serialNumber"), ap.get("deviceName"), ap.get("macAddress"), ap.get("siteId"), ap.get("siteName"), ap.get("deviceGroupName"), ap.get("model"), ap.get("status"), ap.get("firmwareVersion"), ap.get("ipv4"), parse_dt(ap.get("lastSeenAt")), now, raw))
        metric_rows.append((ap_id, bucket_at, ap.get("siteId"), ap.get("cpuUtilization"), ap.get("memoryUtilization"), ap.get("powerConsumption"), ap.get("wlanCount"), ap.get("clientCount"), ap.get("uptimeInMillis"), ap.get("status")))
    with connection() as cnx:
        cur = cnx.cursor()
        if current_rows:
            cur.executemany(AP_CURRENT_SQL, current_rows)
        if metric_rows:
            cur.executemany(AP_METRIC_SQL, metric_rows)
    return len(current_rows) + len(metric_rows)


def process_clients(items: list[dict[str, Any]], collected_at: datetime, bucket_at: datetime) -> int:
    now = utc_now()
    current_rows = []
    summary = Counter()
    names = {}

    for client in items:
        if client.get("siteName") == "Onboarding":
            continue

        client_id = entity_id(client)
        if not client_id:
            continue

        site_id = str(first(client, "siteId", default="") or "")
        connected_serial = str(first(client, "connectedDeviceSerial", "deviceId", "apId", "switchId", default="") or "")
        connected_to = str(first(client, "connectedTo", default="") or "")
        device_id = connected_serial or connected_to
        device_name = first(client, "deviceName", "apName", "switchName")
        connection_type = str(first(client, "clientConnectionType", "connectionType", "type", default="") or "")
        band = str(first(client, "wirelessBand", "band", default="") or "")
        wlan = str(first(client, "wlanName", "ssid", default="") or "")
        raw = json.dumps(client, ensure_ascii=False)

        current_rows.append((
            client_id,
            first(client, "macAddress", "mac"),
            client.get("clientName"),
            first(client, "username", "userName"),
            client.get("hostName"),
            client.get("status"),
            first(client, "ipv4", "ipAddress"),
            client.get("ipv6"),
            site_id,
            client.get("siteName"),
            device_id,
            device_name,
            client.get("connectedDeviceType"),
            connected_serial,
            connected_to,
            client.get("port"),
            client.get("role"),
            connection_type,
            str(client.get("vlanId")) if client.get("vlanId") is not None else None,
            client.get("vlanName"),
            client.get("tunnelType"),
            client.get("tunnelId"),
            wlan,
            band,
            client.get("wirelessChannel"),
            client.get("bssid"),
            client.get("radioMacAddress"),
            client.get("wirelessSecurity"),
            client.get("keyManagement"),
            client.get("authenticationType"),
            client.get("clientCapabilities"),
            client.get("phyType"),
            client.get("snr"),
            client.get("mloOperMode"),
            client.get("clientManufacturer"),
            client.get("clientFunction"),
            client.get("clientVendor"),
            client.get("clientOperatingSystem"),
            client.get("clientCategory"),
            client.get("clientTags"),
            parse_dt(client.get("connectedAt")),
            collected_at,
            parse_dt(first(client, "lastSeenAt", "updatedAt")),
            now,
            raw,
        ))

        key = (site_id, device_id, connection_type, band, wlan)
        summary[key] += 1
        names[key] = (client.get("siteName"), device_name)

    summary_rows = [
        (bucket_at, key[0], names[key][0], key[1], names[key][1], key[2], key[3], key[4], count)
        for key, count in summary.items()
    ]

    with connection() as cnx:
        cur = cnx.cursor()
        if current_rows:
            cur.executemany(CLIENT_CURRENT_SQL, current_rows)
        if summary_rows:
            cur.executemany(CLIENT_SUMMARY_SQL, summary_rows)
    return len(current_rows) + len(summary_rows)


def process_specialized_raw(collector_name: str, items: list[dict[str, Any]], collected_at: datetime) -> int:
    table_name = SPECIALIZED_RAW_TABLES[collector_name]
    now = utc_now()
    rows = []

    for item in items:
        item_id = entity_id(item)
        if not item_id:
            continue
        rows.append((item_id, collected_at, now, json.dumps(item, ensure_ascii=False)))

    if not rows:
        return 0

    sql = f'''
    INSERT INTO {table_name}
    (entity_id, collected_at, updated_at, raw_json)
    VALUES (%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      collected_at=VALUES(collected_at),
      updated_at=VALUES(updated_at),
      raw_json=VALUES(raw_json)
    '''

    with connection() as cnx:
        cur = cnx.cursor()
        cur.executemany(sql, rows)
    return len(rows)


def process_message(collector_name: str, items: list[dict[str, Any]], collected_at: datetime, bucket_at: datetime) -> int:
    written = process_raw(collector_name, items, collected_at, bucket_at)
    if collector_name == "aps":
        written += process_aps(items, collected_at, bucket_at)
    elif collector_name == "clients":
        written += process_clients(items, collected_at, bucket_at)
    elif collector_name in SPECIALIZED_RAW_TABLES:
        written += process_specialized_raw(collector_name, items, collected_at)
    return written
