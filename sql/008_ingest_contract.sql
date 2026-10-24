-- Contrato de ingestão: a fila passa a registrar quem enviou o lote e com qual schema.
-- collector_name continua sendo o event_type e endpoint continua sendo a source,
-- então o worker e os processors existentes seguem funcionando sem mudança.
ALTER TABLE ingestion_queue
  ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default' AFTER id,
  ADD COLUMN IF NOT EXISTS schema_version VARCHAR(16) NOT NULL DEFAULT '1' AFTER collector_name,
  ADD COLUMN IF NOT EXISTS batch_id VARCHAR(128) NULL AFTER schema_version;

CREATE TABLE IF NOT EXISTS collector_keys (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  key_hash CHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL DEFAULT 'default',
  allowed_event_types VARCHAR(500) NOT NULL DEFAULT '*',
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  last_used_at DATETIME(6) NULL,
  UNIQUE KEY uq_collector_keys_hash (key_hash),
  KEY ix_collector_keys_tenant (tenant_id)
) ENGINE=InnoDB;
