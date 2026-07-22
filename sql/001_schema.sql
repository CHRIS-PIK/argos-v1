CREATE TABLE IF NOT EXISTS ingestion_runs (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  collector_name VARCHAR(80) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  finished_at DATETIME(6) NULL,
  status ENUM('RUNNING','SUCCESS','FAILED') NOT NULL,
  pages_processed INT UNSIGNED NOT NULL DEFAULT 0,
  records_received BIGINT UNSIGNED NOT NULL DEFAULT 0,
  records_written BIGINT UNSIGNED NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  KEY ix_runs_collector_started (collector_name, started_at),
  KEY ix_runs_status_started (status, started_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ap_current (
  ap_id VARCHAR(128) NOT NULL,
  serial_number VARCHAR(128) NULL,
  device_name VARCHAR(255) NULL,
  mac_address VARCHAR(64) NULL,
  site_id VARCHAR(128) NULL,
  site_name VARCHAR(255) NULL,
  device_group_name VARCHAR(255) NULL,
  model VARCHAR(255) NULL,
  status VARCHAR(64) NULL,
  firmware_version VARCHAR(128) NULL,
  ipv4 VARCHAR(64) NULL,
  last_seen_at DATETIME(6) NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NULL,
  PRIMARY KEY (ap_id),
  KEY ix_ap_current_site (site_id),
  KEY ix_ap_current_serial (serial_number),
  KEY ix_ap_current_status (status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ap_metrics_10m (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ap_id VARCHAR(128) NOT NULL,
  collected_at DATETIME NOT NULL,
  site_id VARCHAR(128) NULL,
  cpu_utilization DECIMAL(8,3) NULL,
  memory_utilization DECIMAL(8,3) NULL,
  power_consumption DECIMAL(12,3) NULL,
  wlan_count INT NULL,
  client_count INT NULL,
  uptime_ms BIGINT NULL,
  status VARCHAR(64) NULL,
  UNIQUE KEY uq_ap_metric (ap_id, collected_at),
  KEY ix_ap_metrics_time (collected_at),
  KEY ix_ap_metrics_site_time (site_id, collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS client_current (
  client_id VARCHAR(192) NOT NULL,
  mac_address VARCHAR(64) NULL,
  client_name VARCHAR(255) NULL,
  username VARCHAR(255) NULL,
  ip_address VARCHAR(64) NULL,
  site_id VARCHAR(128) NULL,
  site_name VARCHAR(255) NULL,
  device_id VARCHAR(128) NULL,
  device_name VARCHAR(255) NULL,
  connection_type VARCHAR(64) NULL,
  wireless_band VARCHAR(64) NULL,
  wlan_name VARCHAR(255) NULL,
  status VARCHAR(64) NULL,
  first_seen_at DATETIME(6) NULL,
  last_seen_at DATETIME(6) NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NULL,
  PRIMARY KEY (client_id),
  KEY ix_client_current_site (site_id),
  KEY ix_client_current_status (status),
  KEY ix_client_current_mac (mac_address)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS client_summary_10m (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  collected_at DATETIME NOT NULL,
  site_id VARCHAR(128) NOT NULL DEFAULT '',
  site_name VARCHAR(255) NULL,
  device_id VARCHAR(128) NOT NULL DEFAULT '',
  device_name VARCHAR(255) NULL,
  connection_type VARCHAR(64) NOT NULL DEFAULT '',
  wireless_band VARCHAR(64) NOT NULL DEFAULT '',
  wlan_name VARCHAR(255) NOT NULL DEFAULT '',
  connected_clients INT UNSIGNED NOT NULL,
  UNIQUE KEY uq_client_summary (collected_at, site_id, device_id, connection_type, wireless_band, wlan_name),
  KEY ix_client_summary_time (collected_at),
  KEY ix_client_summary_site_time (site_id, collected_at)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW vw_ap_latest AS
SELECT ap_id, serial_number, device_name, site_id, site_name, model, status,
       firmware_version, ipv4, last_seen_at, updated_at
FROM ap_current;

CREATE OR REPLACE VIEW vw_client_summary AS
SELECT collected_at, site_id, site_name, device_id, device_name,
       connection_type, wireless_band, wlan_name, connected_clients
FROM client_summary_10m;
