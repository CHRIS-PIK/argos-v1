CREATE TABLE IF NOT EXISTS switch_current (
  entity_id VARCHAR(192) PRIMARY KEY,
  collected_at DATETIME NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  KEY ix_switch_collected (collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS radio_current (
  entity_id VARCHAR(192) PRIMARY KEY,
  collected_at DATETIME NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  KEY ix_radio_collected (collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS alert_current (
  entity_id VARCHAR(192) PRIMARY KEY,
  collected_at DATETIME NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  KEY ix_alert_collected (collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS license_current (
  entity_id VARCHAR(192) PRIMARY KEY,
  collected_at DATETIME NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  KEY ix_license_collected (collected_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insight_current (
  entity_id VARCHAR(255) PRIMARY KEY,
  scope_type VARCHAR(32) NOT NULL,
  scope_id VARCHAR(192) NOT NULL,
  collected_at DATETIME NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  raw_json JSON NOT NULL,
  KEY ix_insight_scope (scope_type, scope_id),
  KEY ix_insight_collected (collected_at)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW vw_switch_latest AS SELECT entity_id, collected_at, updated_at, raw_json FROM switch_current;
CREATE OR REPLACE VIEW vw_radio_latest AS SELECT entity_id, collected_at, updated_at, raw_json FROM radio_current;
CREATE OR REPLACE VIEW vw_alerts AS SELECT entity_id, collected_at, updated_at, raw_json FROM alert_current;
CREATE OR REPLACE VIEW vw_licenses AS SELECT entity_id, collected_at, updated_at, raw_json FROM license_current;
CREATE OR REPLACE VIEW vw_ai_insights AS SELECT entity_id, scope_type, scope_id, collected_at, updated_at, raw_json FROM insight_current;
