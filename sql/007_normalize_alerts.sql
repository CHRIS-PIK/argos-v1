ALTER TABLE alert_current
  ADD COLUMN IF NOT EXISTS category VARCHAR(128) NULL AFTER entity_id,
  ADD COLUMN IF NOT EXISTS cleared_reason TEXT NULL AFTER category,
  ADD COLUMN IF NOT EXISTS created_at DATETIME(6) NULL AFTER cleared_reason,
  ADD COLUMN IF NOT EXISTS deferred_until VARCHAR(64) NULL AFTER created_at,
  ADD COLUMN IF NOT EXISTS device_type VARCHAR(128) NULL AFTER deferred_until,
  ADD COLUMN IF NOT EXISTS alert_key VARCHAR(128) NULL AFTER device_type,
  ADD COLUMN IF NOT EXISTS name VARCHAR(255) NULL AFTER alert_key,
  ADD COLUMN IF NOT EXISTS notes TEXT NULL AFTER name,
  ADD COLUMN IF NOT EXISTS priority VARCHAR(64) NULL AFTER notes,
  ADD COLUMN IF NOT EXISTS resolved_notes TEXT NULL AFTER priority,
  ADD COLUMN IF NOT EXISTS severity VARCHAR(64) NULL AFTER resolved_notes,
  ADD COLUMN IF NOT EXISTS site_name VARCHAR(255) NULL AFTER severity,
  ADD COLUMN IF NOT EXISTS status VARCHAR(64) NULL AFTER site_name,
  ADD COLUMN IF NOT EXISTS summary TEXT NULL AFTER status,
  ADD COLUMN IF NOT EXISTS api_type VARCHAR(128) NULL AFTER summary,
  ADD COLUMN IF NOT EXISTS source_updated_at DATETIME(6) NULL AFTER api_type,
  ADD COLUMN IF NOT EXISTS updated_by VARCHAR(255) NULL AFTER source_updated_at,
  ADD COLUMN IF NOT EXISTS action_json JSON NULL AFTER updated_by,
  ADD COLUMN IF NOT EXISTS root_cause_json JSON NULL AFTER action_json,
  ADD INDEX IF NOT EXISTS ix_alert_status (status),
  ADD INDEX IF NOT EXISTS ix_alert_severity (severity),
  ADD INDEX IF NOT EXISTS ix_alert_site (site_name),
  ADD INDEX IF NOT EXISTS ix_alert_created (created_at);

UPDATE alert_current
SET
  category = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.category')), 'null'),
  cleared_reason = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.clearedReason')), 'null'),
  created_at = STR_TO_DATE(
    REPLACE(REPLACE(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.createdAt')), 'T', ' '), 'Z', ''),
    '%Y-%m-%d %H:%i:%s.%f'
  ),
  deferred_until = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.deferredUntil')), 'null'),
  device_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.deviceType')), 'null'),
  alert_key = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.key')), 'null'),
  name = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.name')), 'null'),
  notes = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.notes')), 'null'),
  priority = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.priority')), 'null'),
  resolved_notes = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.resolvedNotes')), 'null'),
  severity = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.severity')), 'null'),
  site_name = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.siteName')), 'null'),
  status = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.status')), 'null'),
  summary = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.summary')), 'null'),
  api_type = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.type')), 'null'),
  source_updated_at = STR_TO_DATE(
    REPLACE(REPLACE(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.updatedAt')), 'T', ' '), 'Z', ''),
    '%Y-%m-%d %H:%i:%s.%f'
  ),
  updated_by = NULLIF(JSON_UNQUOTE(JSON_EXTRACT(raw_json, '$.updatedBy')), 'null'),
  action_json = JSON_EXTRACT(raw_json, '$.action'),
  root_cause_json = JSON_EXTRACT(raw_json, '$.rootCause');

CREATE OR REPLACE VIEW vw_alerts AS
SELECT
  entity_id, category, cleared_reason, created_at, deferred_until, device_type,
  alert_key, name, notes, priority, resolved_notes, severity, site_name, status,
  summary, api_type, source_updated_at, updated_by, action_json, root_cause_json,
  collected_at, updated_at
FROM alert_current;
