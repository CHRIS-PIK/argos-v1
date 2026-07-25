ALTER TABLE client_current
  ADD COLUMN IF NOT EXISTS host_name VARCHAR(255) NULL AFTER client_name,
  ADD COLUMN IF NOT EXISTS ipv6 VARCHAR(128) NULL AFTER ip_address,
  ADD COLUMN IF NOT EXISTS connected_device_type VARCHAR(64) NULL AFTER device_name,
  ADD COLUMN IF NOT EXISTS connected_device_serial VARCHAR(128) NULL AFTER connected_device_type,
  ADD COLUMN IF NOT EXISTS connected_to VARCHAR(128) NULL AFTER connected_device_serial,
  ADD COLUMN IF NOT EXISTS port VARCHAR(128) NULL AFTER connected_to,
  ADD COLUMN IF NOT EXISTS role VARCHAR(128) NULL AFTER port,
  ADD COLUMN IF NOT EXISTS vlan_id VARCHAR(64) NULL AFTER connection_type,
  ADD COLUMN IF NOT EXISTS vlan_name VARCHAR(255) NULL AFTER vlan_id,
  ADD COLUMN IF NOT EXISTS tunnel_type VARCHAR(64) NULL AFTER vlan_name,
  ADD COLUMN IF NOT EXISTS tunnel_id BIGINT NULL AFTER tunnel_type,
  ADD COLUMN IF NOT EXISTS wireless_channel INT NULL AFTER wireless_band,
  ADD COLUMN IF NOT EXISTS bssid VARCHAR(64) NULL AFTER wireless_channel,
  ADD COLUMN IF NOT EXISTS radio_mac_address VARCHAR(64) NULL AFTER bssid,
  ADD COLUMN IF NOT EXISTS wireless_security VARCHAR(128) NULL AFTER radio_mac_address,
  ADD COLUMN IF NOT EXISTS key_management VARCHAR(128) NULL AFTER wireless_security,
  ADD COLUMN IF NOT EXISTS authentication_type VARCHAR(128) NULL AFTER key_management,
  ADD COLUMN IF NOT EXISTS client_capabilities VARCHAR(255) NULL AFTER authentication_type,
  ADD COLUMN IF NOT EXISTS phy_type VARCHAR(64) NULL AFTER client_capabilities,
  ADD COLUMN IF NOT EXISTS snr DECIMAL(8,2) NULL AFTER phy_type,
  ADD COLUMN IF NOT EXISTS mlo_oper_mode VARCHAR(128) NULL AFTER snr,
  ADD COLUMN IF NOT EXISTS client_manufacturer VARCHAR(255) NULL AFTER mlo_oper_mode,
  ADD COLUMN IF NOT EXISTS client_function VARCHAR(255) NULL AFTER client_manufacturer,
  ADD COLUMN IF NOT EXISTS client_vendor VARCHAR(255) NULL AFTER client_function,
  ADD COLUMN IF NOT EXISTS client_operating_system VARCHAR(255) NULL AFTER client_vendor,
  ADD COLUMN IF NOT EXISTS client_category VARCHAR(255) NULL AFTER client_operating_system,
  ADD COLUMN IF NOT EXISTS client_tags TEXT NULL AFTER client_category,
  ADD COLUMN IF NOT EXISTS connected_at DATETIME(6) NULL AFTER client_tags,
  ADD INDEX IF NOT EXISTS ix_client_connection_type (connection_type),
  ADD INDEX IF NOT EXISTS ix_client_device_serial (connected_device_serial),
  ADD INDEX IF NOT EXISTS ix_client_last_seen (last_seen_at),
  ADD INDEX IF NOT EXISTS ix_client_site_status (site_id, status);

UPDATE client_current
SET
  host_name = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.hostName')), 'null'),
  ip_address = COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.ipv4')), 'null'), ip_address),
  ipv6 = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.ipv6')), 'null'),
  connected_device_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceType')), 'null'),
  connected_device_serial = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceSerial')), 'null'),
  connected_to = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedTo')), 'null'),
  port = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.port')), 'null'),
  role = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.role')), 'null'),
  vlan_id = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.vlanId')), 'null'),
  vlan_name = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.vlanName')), 'null'),
  tunnel_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.tunnelType')), 'null'),
  tunnel_id = CAST(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.tunnelId')), 'null'), '') AS SIGNED),
  wireless_channel = CAST(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.wirelessChannel')), 'null'), '') AS SIGNED),
  bssid = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.bssid')), 'null'),
  radio_mac_address = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.radioMacAddress')), 'null'),
  wireless_security = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.wirelessSecurity')), 'null'),
  key_management = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.keyManagement')), 'null'),
  authentication_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.authenticationType')), 'null'),
  client_capabilities = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientCapabilities')), 'null'),
  phy_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.phyType')), 'null'),
  snr = CAST(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.snr')), 'null'), '') AS DECIMAL(8,2)),
  mlo_oper_mode = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.mloOperMode')), 'null'),
  client_manufacturer = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientManufacturer')), 'null'),
  client_function = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientFunction')), 'null'),
  client_vendor = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientVendor')), 'null'),
  client_operating_system = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientOperatingSystem')), 'null'),
  client_category = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientCategory')), 'null'),
  client_tags = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clientTags')), 'null'),
  connected_at = CASE
    WHEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')), 'null'), '') IS NULL
      THEN connected_at
    ELSE STR_TO_DATE(
      REPLACE(
        REPLACE(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedAt')), 'T', ' '),
        'Z',
        ''
      ),
      '%Y-%m-%d %H:%i:%s.%f'
    )
  END,
  device_id = COALESCE(
    NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedDeviceSerial')), 'null'), ''),
    NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.connectedTo')), 'null'), ''),
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
