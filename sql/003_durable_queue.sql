CREATE TABLE IF NOT EXISTS ingestion_queue (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  collector_name VARCHAR(80) NOT NULL,
  endpoint VARCHAR(500) NOT NULL,
  page_number INT UNSIGNED NOT NULL DEFAULT 1,
  collected_at DATETIME(6) NOT NULL,
  bucket_at DATETIME NOT NULL,
  payload JSON NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  dedup_key CHAR(64) NOT NULL,
  status ENUM('PENDING','PROCESSING','PROCESSED','FAILED','DEAD') NOT NULL DEFAULT 'PENDING',
  attempts INT UNSIGNED NOT NULL DEFAULT 0,
  available_at DATETIME(6) NOT NULL,
  locked_at DATETIME(6) NULL,
  locked_by VARCHAR(128) NULL,
  processed_at DATETIME(6) NULL,
  error_message TEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_ingestion_queue_dedup (dedup_key),
  KEY ix_ingestion_queue_claim (status, available_at, id),
  KEY ix_ingestion_queue_locked (status, locked_at),
  KEY ix_ingestion_queue_collector_time (collector_name, collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS raw_entity_current (
  collector_name VARCHAR(80) NOT NULL,
  entity_id VARCHAR(255) NOT NULL,
  site_id VARCHAR(128) NULL,
  site_name VARCHAR(255) NULL,
  entity_name VARCHAR(255) NULL,
  status VARCHAR(64) NULL,
  source_collected_at DATETIME(6) NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  PRIMARY KEY (collector_name, entity_id),
  KEY ix_raw_entity_site (collector_name, site_id),
  KEY ix_raw_entity_status (collector_name, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS raw_entity_snapshot_10m (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  collector_name VARCHAR(80) NOT NULL,
  entity_id VARCHAR(255) NOT NULL,
  collected_at DATETIME NOT NULL,
  site_id VARCHAR(128) NULL,
  status VARCHAR(64) NULL,
  raw_json JSON NOT NULL,
  UNIQUE KEY uq_raw_entity_snapshot (collector_name, entity_id, collected_at),
  KEY ix_raw_snapshot_time (collected_at),
  KEY ix_raw_snapshot_collector_time (collector_name, collected_at)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW vw_ingestion_queue_health AS
SELECT collector_name,
       status,
       COUNT(*) AS messages,
       MIN(created_at) AS oldest_message,
       MAX(created_at) AS newest_message,
       MAX(attempts) AS max_attempts
FROM ingestion_queue
GROUP BY collector_name, status;

CREATE OR REPLACE VIEW vw_raw_entity_latest AS
SELECT collector_name, entity_id, site_id, site_name, entity_name, status,
       source_collected_at, updated_at, raw_json
FROM raw_entity_current;
