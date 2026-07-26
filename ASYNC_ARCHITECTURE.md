# Arquitetura assíncrona, durável e observável

O Argos separa coleta, persistência intermediária e processamento em serviços independentes. Essa divisão evita que instabilidades da API, banco ou processadores interrompam toda a esteira e permite escalar producer e worker de forma separada.

```text
Aruba New Central
      |
      v
producer
  - autenticação
  - paginação
  - retry/backoff
  - validação
  - hash do payload
      |
      v
ingestion_queue (MariaDB)
  PENDING -> PROCESSING -> PROCESSED
                  |
                  +-> FAILED -> DEAD
      |
      v
worker(s)
  - claim concorrente
  - normalização
  - UPSERT idempotente
  - histórico e snapshots
      |
      v
tabelas current + históricos + raw_entity_*
```

Paralelamente:

```text
producer :9101 ----\
                   > Grafana Alloy -> Mimir -> Grafana
worker   :9102 ----/
```

## Responsabilidades

### Producer

- obtém e renova tokens;
- percorre todas as páginas dos endpoints configurados;
- respeita timeout, retry, backoff e `Retry-After`;
- interrompe paginações anômalas por limite máximo de páginas ou payload repetido;
- calcula hash canônico do payload;
- persiste cada página na fila antes de continuar;
- expõe métricas Prometheus na porta configurada, por padrão `9101`.

### Fila persistente

A tabela `ingestion_queue` desacopla a velocidade de coleta da velocidade de processamento.

Estados:

- `PENDING`: disponível para processamento;
- `PROCESSING`: reclamada por um worker, com lock e lease;
- `PROCESSED`: concluída com sucesso;
- `FAILED`: falha temporária, aguardando nova tentativa;
- `DEAD`: falha definitiva após atingir o limite de tentativas.

A deduplicação considera coletor, endpoint, bucket, página e hash do payload.

### Worker

- reclama a próxima mensagem elegível usando `FOR UPDATE SKIP LOCKED`;
- desserializa e valida o payload;
- encaminha os itens ao processor do collector;
- grava snapshots atuais por `UPSERT`;
- grava históricos de forma idempotente;
- atualiza o estado da fila;
- recupera automaticamente locks expirados;
- expõe métricas Prometheus na porta configurada, por padrão `9102`.

## Garantias

- cada página recebida da API é persistida antes do processamento;
- o processamento é `at least once`;
- as escritas finais usam `UPSERT`, tornando reprocessamentos seguros;
- mensagens com falha usam backoff exponencial;
- mensagens excedendo o limite de tentativas vão para `DEAD`;
- mensagens presas em `PROCESSING` voltam ao fluxo após expiração do lock;
- payloads repetidos não criam novas mensagens equivalentes;
- limites de paginação impedem ciclos infinitos;
- dados ainda não normalizados são preservados nas tabelas `raw_entity_*`.

## Concorrência

É possível executar múltiplos workers:

```bash
docker compose up -d --build --scale worker=2
```

Como o claim usa `SKIP LOCKED`, workers diferentes não processam intencionalmente a mesma mensagem ao mesmo tempo. A garantia continua sendo `at least once`, portanto os processors devem permanecer idempotentes.

## Aplicar migration em banco existente

```bash
set -a
source .env
set +a

docker exec -i aruba-mariadb mariadb \
  -uroot -p"$DB_ROOT_PASSWORD" "$DB_NAME" \
  < sql/003_durable_queue.sql
```

As migrations devem ser idempotentes e aplicadas antes da recriação dos serviços.

## Subir ou recriar a esteira

```bash
docker compose up -d --build producer worker
```

Em hosts com pouca memória:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose build producer
COMPOSE_PARALLEL_LIMIT=1 docker compose build worker
docker compose up -d --force-recreate producer worker
```

Acompanhar:

```bash
docker compose ps
docker compose logs -f producer worker
```

## Saúde da fila

Resumo atual:

```sql
SELECT * FROM vw_ingestion_queue_health;
```

Contagem direta por status:

```sql
SELECT status, COUNT(*) AS total
FROM ingestion_queue
GROUP BY status
ORDER BY status;
```

Mensagens mortas:

```sql
SELECT
    id,
    collector_name,
    endpoint,
    page_number,
    attempts,
    error_message,
    created_at,
    updated_at
FROM ingestion_queue
WHERE status = 'DEAD'
ORDER BY id DESC;
```

Reprocessar uma mensagem morta:

```sql
UPDATE ingestion_queue
SET status = 'PENDING',
    attempts = 0,
    available_at = NOW(6),
    locked_at = NULL,
    locked_by = NULL,
    error_message = NULL
WHERE id = <ID>;
```

Faça esse reprocessamento apenas depois de corrigir a causa da falha.

## Métricas Prometheus

### Producer

- `datalake_producer_cycles_total{status}`
- `datalake_pages_collected_total{collector}`
- `datalake_pages_queued_total{collector}`
- `datalake_collection_duration_seconds{collector}`
- `datalake_last_success_timestamp_seconds{collector}`
- `datalake_pagination_stops_total{collector,reason}`
- `aruba_requests_total{endpoint,method,status}`
- `aruba_request_errors_total{endpoint,error_type}`
- `aruba_request_duration_seconds{endpoint,method}`

### Worker e fila

- `datalake_messages_total{collector,status}`
- `datalake_items_processed_total{collector}`
- `datalake_records_written_total{collector}`
- `datalake_processing_duration_seconds{collector}`
- `datalake_stale_messages_recovered_total`
- `datalake_queue_messages{status}`
- `datalake_queue_backlog`
- `datalake_queue_oldest_pending_age_seconds`

Validação local:

```bash
curl -s http://localhost:9101/metrics | grep -E 'datalake_|aruba_' | head
curl -s http://localhost:9102/metrics | grep -E 'datalake_' | head
```

## Consultas operacionais úteis

Producer e worker disponíveis:

```promql
up{job=~"datalake-producer|datalake-worker"}
```

Backlog:

```promql
datalake_queue_backlog
```

Idade do item mais antigo:

```promql
datalake_queue_oldest_pending_age_seconds
```

P95 de processamento:

```promql
histogram_quantile(
  0.95,
  sum by (le, collector) (
    rate(datalake_processing_duration_seconds_bucket[5m])
  )
)
```

Tempo desde a última coleta bem-sucedida:

```promql
time() - datalake_last_success_timestamp_seconds
```

## Modelo de dados resultante

APs e clientes possuem modelos normalizados específicos. Switches, rádios, alertas, licenças e insights também possuem tabelas atuais ou views próprias. O payload bruto continua preservado para auditoria e para evolução dos modelos sem perda de evidência.

As principais classes de armazenamento são:

- `*_current`: snapshot atual;
- `*_10m`: histórico agregado ou amostrado em buckets;
- `raw_entity_current`: snapshot bruto atual;
- `raw_entity_snapshot_10m`: histórico bruto;
- `vw_*`: camada estável de consumo.
