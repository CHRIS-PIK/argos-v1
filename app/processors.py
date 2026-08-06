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
    "radios": "radio_current",
}

SWITCH_CURRENT_SQL = '''
INSERT INTO switch_current
(entity_id,deployment,status,firmware_version,ipv4,ipv6,public_ip,mac_address,
 stack_id,stack_member_id,switch_type,serial_number,switch_role,site_id,site_name,
 device_name,model,j_number,api_type,last_seen_at,uptime_ms,cpu_utilization,
 memory_utilization,power_consumption,system_temperature,poe_available,
 poe_consumption,total_power_consumption,uplink_ports,usage_value,
 collected_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 deployment=VALUES(deployment),status=VALUES(status),
 firmware_version=VALUES(firmware_version),ipv4=VALUES(ipv4),ipv6=VALUES(ipv6),
 public_ip=VALUES(public_ip),mac_address=VALUES(mac_address),stack_id=VALUES(stack_id),
 stack_member_id=VALUES(stack_member_id),switch_type=VALUES(switch_type),
 serial_number=VALUES(serial_number),switch_role=VALUES(switch_role),
 site_id=VALUES(site_id),site_name=VALUES(site_name),device_name=VALUES(device_name),
 model=VALUES(model),j_number=VALUES(j_number),api_type=VALUES(api_type),
 last_seen_at=VALUES(last_seen_at),uptime_ms=VALUES(uptime_ms),
 cpu_utilization=VALUES(cpu_utilization),memory_utilization=VALUES(memory_utilization),
 power_consumption=VALUES(power_consumption),system_temperature=VALUES(system_temperature),
 poe_available=VALUES(poe_available),poe_consumption=VALUES(poe_consumption),
 total_power_consumption=VALUES(total_power_consumption),uplink_ports=VALUES(uplink_ports),
 usage_value=VALUES(usage_value),collected_at=VALUES(collected_at),
 updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
'''

ALERT_CURRENT_SQL = '''
INSERT INTO alert_current
(entity_id,category,cleared_reason,created_at,deferred_until,device_type,
 alert_key,name,notes,priority,resolved_notes,severity,site_name,status,summary,
 api_type,source_updated_at,updated_by,action_json,root_cause_json,
 collected_at,updated_at,raw_json)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON DUPLICATE KEY UPDATE
 category=VALUES(category),cleared_reason=VALUES(cleared_reason),
 created_at=VALUES(created_at),deferred_until=VALUES(deferred_until),
 device_type=VALUES(device_type),alert_key=VALUES(alert_key),name=VALUES(name),
 notes=VALUES(notes),priority=VALUES(priority),resolved_notes=VALUES(resolved_notes),
 severity=VALUES(severity),site_name=VALUES(site_name),status=VALUES(status),
 summary=VALUES(summary),api_type=VALUES(api_type),
 source_updated_at=VALUES(source_updated_at),updated_by=VALUES(updated_by),
 action_json=VALUES(action_json),root_cause_json=VALUES(root_cause_json),
 collected_at=VALUES(collected_at),updated_at=VALUES(updated_at),raw_json=VALUES(raw_json)
'''


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


def process_switches(items: list[dict[str, Any]], collected_at: datetime) -> int:
    now = utc_now()
    rows = []
    for switch in items:
        switch_id = entity_id(switch)
        if not switch_id or switch.get("siteName") == "Onboarding":
            continue
        trends = switch.get("switchTrends") or []
        trend = trends[0] if trends and isinstance(trends[0], dict) else {}
        rows.append((
            switch_id, switch.get("deployment"), switch.get("status"),
            switch.get("firmwareVersion"), switch.get("ipv4"), switch.get("ipv6"),
            switch.get("publicIp"), switch.get("macAddress"), switch.get("stackId"),
            switch.get("stackMemberId"), switch.get("switchType"), switch.get("serialNumber"),
            switch.get("switchRole"), switch.get("siteId"), switch.get("siteName"),
            switch.get("deviceName"), switch.get("model"), switch.get("jNumber"),
            switch.get("type"), parse_dt(switch.get("lastSeenAt")),
            switch.get("uptimeInMillis"), trend.get("cpuUtilization"),
            trend.get("memoryUtilization"), trend.get("powerConsumption"),
            trend.get("systemTemperature"), trend.get("poeAvailable"),
            trend.get("poeConsumption"), trend.get("totalPowerConsumption"),
            trend.get("upLinkPorts"), trend.get("usage"), collected_at, now,
            json.dumps(switch, ensure_ascii=False),
        ))
    if rows:
        with connection() as cnx:
            cnx.cursor().executemany(SWITCH_CURRENT_SQL, rows)
    return len(rows)


def process_alerts(items: list[dict[str, Any]], collected_at: datetime) -> int:
    now = utc_now()
    rows = []
    for alert in items:
        alert_id = entity_id(alert)
        if not alert_id:
            continue
        rows.append((
            alert_id, alert.get("category"), alert.get("clearedReason"),
            parse_dt(alert.get("createdAt")), str(alert.get("deferredUntil") or ""),
            alert.get("deviceType"), alert.get("key"), alert.get("name"),
            alert.get("notes"), alert.get("priority"), alert.get("resolvedNotes"),
            alert.get("severity"), alert.get("siteName"), alert.get("status"),
            alert.get("summary"), alert.get("type"), parse_dt(alert.get("updatedAt")),
            alert.get("updatedBy"), json.dumps(alert.get("action"), ensure_ascii=False),
            json.dumps(alert.get("rootCause"), ensure_ascii=False), collected_at, now,
            json.dumps(alert, ensure_ascii=False),
        ))
    if rows:
        with connection() as cnx:
            cnx.cursor().executemany(ALERT_CURRENT_SQL, rows)
    return len(rows)


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
    elif collector_name == "switches":
        written += process_switches(items, collected_at)
    elif collector_name == "alerts":
        written += process_alerts(items, collected_at)
    elif collector_name in SPECIALIZED_RAW_TABLES:
        written += process_specialized_raw(collector_name, items, collected_at)
    return written
