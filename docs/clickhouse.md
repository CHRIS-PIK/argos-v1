# Armazenamento no ClickHouse

O worker grava cada item validado em duas tabelas. O MariaDB não faz mais parte da plataforma.

```text
Redis Streams -> worker -> argos.events        (histórico)
                        -> argos.entity_latest (estado atual)
```

O schema fica em `clickhouse/001_events.sql` e é aplicado na primeira subida do volume. Em um volume já existente (ou se o schema mudar durante o desenvolvimento), recrie o volume ou aplique manualmente:

```bash
docker compose exec -T clickhouse clickhouse-client --multiquery < clickhouse/001_events.sql
```

## Tabelas

| Tabela | Conteúdo | Chave |
|---|---|---|
| `argos.events` | Um registro por entidade por bucket de 10 min. TTL de 90 dias. | `(tenant_id, event_type, source, entity_id, bucket_at)` |
| `argos.entity_latest` | Última versão de cada entidade. | `(tenant_id, event_type, source, entity_id)` |
| `argos.v_entity_latest` | `entity_latest FINAL`, já deduplicada. | |

Colunas: `tenant_id`, `source`, `event_type`, `schema_version`, `entity_id`, `collected_at`, `ingested_at`, `name`, `status`, `dimensions` (`Map(String, String)`), `batch_id` e `payload` (o item original em JSON).

`entity_id`, `name`, `status` e `dimensions` são extraídos pelo mapeamento `x-argos` do schema do tipo. Nenhuma coluna tem nome de uma fonte específica; o que for particular de uma fonte (site, região, centro de custo...) entra em `dimensions`.

Ambas usam `ReplacingMergeTree`: gravar de novo a mesma chave substitui a linha na fusão em segundo plano, o que torna o reprocessamento de uma mensagem idempotente. Por isso leia sempre com `FINAL`, `argMax` ou pela view.

## Consultas

Estado atual de entidades com problema, de qualquer fonte:

```sql
SELECT source, entity_id, name, status, dimensions['site_name'] AS site
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

## Limites

- Sem backfill de dados antigos (o MariaDB foi descartado).
- O payload é guardado como texto; tabelas colunares por tipo podem ser criadas depois com materialized views, quando houver consultas que as justifiquem.
- Instância única, sem réplica nem shard. Para Kubernetes, usar o operador do ClickHouse numa fase própria.
- Se a escrita no ClickHouse falhar, a mensagem fica pendente no Redis e é reprocessada; depois de `QUEUE_MAX_ATTEMPTS` falhas vai para `argos:events:dead`.
