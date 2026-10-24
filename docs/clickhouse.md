# Armazenamento no ClickHouse (fase 2)

O worker passa a gravar também no ClickHouse, em **escrita dupla**: o MariaDB continua sendo gravado como antes, então Power BI e views existentes não mudam. A escrita no ClickHouse é desligada por padrão.

```text
ingestion_queue -> worker -+-> MariaDB (tabelas atuais, históricos, views)
                           +-> ClickHouse (events, entity_latest)   [CLICKHOUSE_ENABLED=true]
```

## Ativação

1. `docker compose up -d clickhouse` (o schema de `clickhouse/001_events.sql` é aplicado na primeira subida do volume).
2. No `.env`: `CLICKHOUSE_ENABLED=true` (e usuário/senha, se houver).
3. `docker compose up -d --build worker`.

Em volume já existente, aplique o schema manualmente:

```bash
docker compose exec -T clickhouse clickhouse-client --multiquery < clickhouse/001_events.sql
```

Se a escrita no ClickHouse falhar, a mensagem volta para a fila (`FAILED`) e é reprocessada; os UPSERTs do MariaDB e a deduplicação do ClickHouse tornam isso seguro.

## Tabelas

| Tabela | Conteúdo | Chave |
|---|---|---|
| `argos.events` | Um registro por entidade por bucket de 10 min. TTL de 90 dias. | `(tenant_id, event_type, source, entity_id, bucket_at)` |
| `argos.entity_latest` | Última versão de cada entidade. | `(tenant_id, event_type, source, entity_id)` |
| `argos.v_entity_latest` | `entity_latest FINAL`, já deduplicada. | |

Ambas usam `ReplacingMergeTree`: gravar de novo a mesma chave substitui a linha (na fusão em segundo plano). Por isso leia sempre com `FINAL`, `argMax` ou pela view. `tenant_id` e `source` fazem parte da chave, o que elimina a colisão que existe em `raw_entity_current`.

O item original fica em `payload` (JSON como texto). Campos comuns (`site_id`, `site_name`, `entity_name`, `status`) são extraídos para colunas.

## Consultas

Estado atual de APs com problema:

```sql
SELECT entity_id, entity_name, site_name, status
FROM argos.v_entity_latest
WHERE tenant_id = 'default' AND event_type = 'aps' AND status != 'Up';
```

Série de um campo do payload:

```sql
SELECT bucket_at, JSONExtractFloat(payload, 'cpuUtilization') AS cpu
FROM argos.events FINAL
WHERE entity_id = 'ap-1' AND bucket_at >= now() - INTERVAL 1 DAY
ORDER BY bucket_at;
```

## Limites desta fase

- Só dados novos são gravados; não há backfill do histórico do MariaDB.
- Hoje o ClickHouse guarda o payload bruto. Tabelas colunares por tipo (equivalentes a `ap_metrics_10m`) podem vir via materialized views quando houver consultas que as justifiquem.
- Sem réplica nem shard: instância única. Para Kubernetes, usar o operador do ClickHouse numa fase própria.
- O MariaDB só sai do caminho depois de validar os números lado a lado (contagem de entidades por tipo e por bucket).
