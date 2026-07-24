ALTER TABLE client_current
  ADD COLUMN host_name VARCHAR(255) NULL AFTER client_name,
  ADD COLUMN ipv6 VARCHAR(128) NULL AFTER ip_address,
  ADD COLUMN connected_device_type VARCHAR(64) NULL AFTER device_name,
  ADD COLUMN connected_device_serial VARCHAR(128) NULL AFTER connected_device_type,
  ADD COLUMN connected_to VARCHAR(128) NULL AFTER connected_device_serial,
  ADD COLUMN port VARCHAR(128) NULL AFTER connected_to,
  ADD COLUMN role VARCHAR(128) NULL AFTER port,
  ADD COLUMN vlan_id VARCHAR(64) NULL AFTER connection_type,
  ADD COLUMN vlan_name VARCHAR(255) NULL AFTER vlan_id,
  ADD COLUMN tunnel_type VARCHAR(64) NULL AFTER vlan_name,
  ADD COLUMN tunnel_id BIGINT NULL AFTER tunnel_type,
  ADD COLUMN wireless_channel INT NULL AFTER wireless_band,
  ADD COLUMN bssid VARCHAR(64) NULL AFTER wireless_channel,
  ADD COLUMN radio_mac_address VARCHAR(64) NULL AFTER bssid,
  ADD COLUMN wireless_security VARCHAR(128) NULL AFTER radio_mac_address,
  ADD COLUMN key_management VARCHAR(128) NULL AFTER wireless_security,
  ADD COLUMN authentication_type VARCHAR(128) NULL AFTER key_management,
  ADD COLUMN client_capabilities VARCHAR(255) NULL AFTER authentication_type,
  ADD COLUMN phy_type VARCHAR(64) NULL AFTER client_capabilities,
  ADD COLUMN snr DECIMAL(8,2) NULL AFTER phy_type,
  ADD COLUMN mlo_oper_mode VARCHAR(128) NULL AFTER snr,
  ADD COLUMN client_manufacturer VARCHAR(255) NULL AFTER mlo_oper_mode,
  ADD COLUMN client_function VARCHAR(255) NULL AFTER client_manufacturer,
  ADD COLUMN client_vendor VARCHAR(255) NULL AFTER client_function,
  ADD COLUMN client_operating_system VARCHAR(255) NULL AFTER client_vendor,
  ADD COLUMN client_category VARCHAR(255) NULL AFTER client_operating_system,
  ADD COLUMN client_tags TEXT NULL AFTER client_category,
  ADD COLUMN connected_at DATETIME(6) NULL AFTER client_tags,
  ADD KEY ix_client_connection_type (connection_type),
  ADD KEY ix_client_device_serial (connected_device_serial),
  ADD KEY ix_client_last_seen (last_seen_at),
  ADD KEY ix_client_site_status (site_id, status);

UPDATE client_current
SET
  host_name = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.hostName')),
  ip_address = COALESCE(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.ipv4')), ip_address),
  ipv6 = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.ipv6')),
  connected_device_type = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceType')),
  connected_device_serial = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceSerial')),
  connected_to = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedTo')),
  port = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.port')),
  role = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.role')),
  vlan_id = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.vlanId')),
  vlan_name = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.vlanName')),
  tunnel_type = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.tunnelType')),
  tunnel_id = CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.tunnelId')) AS SIGNED),
  wireless_channel = CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.wirelessChannel')) AS SIGNED),
  bssid = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.bssid')),
  radio_mac_address = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.radioMacAddress')),
  wireless_security = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.wirelessSecurity')),
  key_management = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.keyManagement')),
  authentication_type = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.authenticationType')),
  client_capabilities = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientCapabilities')),
  phy_type = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.phyType')),
  snr = CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.snr')) AS DECIMAL(8,2)),
  mlo_oper_mode = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.mloOperMode')),
  client_manufacturer = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientManufacturer')),
  client_function = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientFunction')),
  client_vendor = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientVendor')),
  client_operating_system = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientOperatingSystem')),
  client_category = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientCategory')),
  client_tags = JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientTags')),
  connected_at = CASE
    WHEN JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')) IS NULL THEN connected_at
    ELSE STR_TO_DATE(
      REPLACE(SUBSTRING(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')), 1, 26), 'T', ' '),
      '%Y-%m-%d %H:%i:%s.%f'
    )
  END,
  device_id = COALESCE(
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceSerial')), ''),
    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedTo')), ''),
    device_id
  );

INSERT INTO switch_current (entity_id, collected_at, updated_at, raw_json)
SELECT entity_id, source_collected_at, updated_at, raw_json
FROM raw_entity_current
WHERE collector_name = 'switches'
ON DUPLICATE KEY UPDATE
  collected_at = VALUES(collected_at),
  updated_at = VALUES(updated_at),
  raw_json = VALUES(raw_json);

INSERT INTO radio_current (entity_id, collected_at, updated_at, raw_json)
SELECT entity_id, source_collected_at, updated_at, raw_json
FROM raw_entity_current
WHERE collector_name = 'radios'
ON DUPLICATE KEY UPDATE
  collected_at = VALUES(collected_at),
  updated_at = VALUES(updated_at),
  raw_json = VALUES(raw_json);

INSERT INTO alert_current (entity_id, collected_at, updated_at, raw_json)
SELECT entity_id, source_collected_at, updated_at, raw_json
FROM raw_entity_current
WHERE collector_name = 'alerts'
ON DUPLICATE KEY UPDATE
  collected_at = VALUES(collected_at),
  updated_at = VALUES(updated_at),
  raw_json = VALUES(raw_json);

CREATE OR REPLACE VIEW vw_client_latest AS
SELECT
  client_id,
  mac_address,
  client_name,
  username,
  host_name,
  status,
  ip_address AS ipv4,
  ipv6,
  site_id,
  site_name,
  connected_device_type,
  connected_device_serial,
  connected_to,
  port,
  role,
  connection_type,
  vlan_id,
  vlan_name,
  tunnel_type,
  tunnel_id,
  wlan_name,
  wireless_band,
  wireless_channel,
  bssid,
  radio_mac_address,
  wireless_security,
  key_management,
  authentication_type,
  client_capabilities,
  phy_type,
  snr,
  mlo_oper_mode,
  client_manufacturer,
  client_function,
  client_vendor,
  client_operating_system,
  client_category,
  client_tags,
  connected_at,
  first_seen_at,
  last_seen_at,
  updated_at
FROM client_current;
