CREATE DATABASE IF NOT EXISTS argos;

-- Histórico: um registro por entidade por bucket de 10 minutos.
-- ReplacingMergeTree com a chave de ordenação como chave de deduplicação torna
-- a reprocessamento da mesma mensagem idempotente (mesmo papel do UNIQUE KEY do MariaDB).
CREATE TABLE IF NOT EXISTS argos.events
(
    tenant_id      LowCardinality(String),
    source         LowCardinality(String),
    event_type     LowCardinality(String),
    schema_version LowCardinality(String),
    entity_id      String,
    bucket_at      DateTime('UTC'),
    collected_at   DateTime64(3, 'UTC'),
    ingested_at    DateTime64(3, 'UTC'),
    site_id        String,
    site_name      String,
    entity_name    String,
    status         LowCardinality(String),
    batch_id       String,
    payload        String CODEC(ZSTD(3))
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(bucket_at)
ORDER BY (tenant_id, event_type, source, entity_id, bucket_at)
TTL toDateTime(bucket_at) + INTERVAL 90 DAY;

-- Estado atual: a última versão de cada entidade, isolada por tenant e source.
-- Resolve a colisão de raw_entity_current entre sources com o mesmo event_type.
CREATE TABLE IF NOT EXISTS argos.entity_latest
(
    tenant_id      LowCardinality(String),
    source         LowCardinality(String),
    event_type     LowCardinality(String),
    schema_version LowCardinality(String),
    entity_id      String,
    collected_at   DateTime64(3, 'UTC'),
    ingested_at    DateTime64(3, 'UTC'),
    site_id        String,
    site_name      String,
    entity_name    String,
    status         LowCardinality(String),
    batch_id       String,
    payload        String CODEC(ZSTD(3))
)
ENGINE = ReplacingMergeTree(collected_at)
ORDER BY (tenant_id, event_type, source, entity_id);

CREATE VIEW IF NOT EXISTS argos.v_entity_latest AS
SELECT * FROM argos.entity_latest FINAL;
