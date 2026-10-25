# Observabilidade (Alloy e Grafana)

O Argos expõe métricas Prometheus, escreve logs em `stdout`, envia traces por OTLP e perfis ao Pyroscope. O Alloy (que não faz parte deste repo) é quem coleta métricas e logs.

## Alvos de métricas

| Serviço | Container | Endereço | Observação |
|---|---|---|---|
| Ingest API | `argos-ingest` | `:8000/metrics` | `argos_ingest_*` |
| Query API | `argos-query` | `:8001/metrics` | |
| Worker | `aruba-worker` | `:9102/metrics` | `datalake_*` (inalterado) |
| Coletor Aruba | `argos-collector-aruba` | `:9101/metrics` | `argos_collector_*`, `aruba_*` |
| Coletor demo | `argos-collector-demo` | `:9103/metrics` | `argos_demo_*` (profile `demo`) |

As portas podem ser trocadas no `.env` (`INGEST_PORT`, `QUERY_PORT`, `DEMO_PORT`).

## Ajuste no `config.alloy`

### 1. Rótulos dos logs

As duas regras que usam `regex = "/(aruba-producer|aruba-worker|aruba-mariadb)"` passam a:

```alloy
regex = "/(argos-.*|aruba-worker|aruba-producer|aruba-mariadb)"
```

(Os nomes antigos podem ficar para não perder o histórico de logs.)

### 2. Raspagem

Troque o bloco `prometheus.scrape "datalake_producer"` pelos quatro abaixo e mantenha o `datalake_worker` como está:

```alloy
prometheus.scrape "argos_collector_aruba" {
  targets = [
    {
      "__address__" = "host.docker.internal:9101",
      "job"         = "argos-collector-aruba",
      "service"     = "argos",
      "component"   = "collector",
    },
  ]

  scrape_interval = "15s"
  scrape_timeout  = "10s"

  forward_to = [
    prometheus.remote_write.mimir.receiver,
  ]
}

prometheus.scrape "argos_ingest" {
  targets = [
    {
      "__address__" = "host.docker.internal:8000",
      "job"         = "argos-ingest",
      "service"     = "argos",
      "component"   = "ingest",
    },
  ]

  scrape_interval = "15s"
  scrape_timeout  = "10s"

  forward_to = [
    prometheus.remote_write.mimir.receiver,
  ]
}

prometheus.scrape "argos_query" {
  targets = [
    {
      "__address__" = "host.docker.internal:8001",
      "job"         = "argos-query",
      "service"     = "argos",
      "component"   = "query",
    },
  ]

  scrape_interval = "15s"
  scrape_timeout  = "10s"

  forward_to = [
    prometheus.remote_write.mimir.receiver,
  ]
}

prometheus.scrape "argos_collector_demo" {
  targets = [
    {
      "__address__" = "host.docker.internal:9103",
      "job"         = "argos-collector-demo",
      "service"     = "argos",
      "component"   = "collector",
    },
  ]

  scrape_interval = "60s"
  scrape_timeout  = "10s"

  forward_to = [
    prometheus.remote_write.mimir.receiver,
  ]
}
```

### 3. Aplicar

```bash
sudo nano /opt/docker/stacks/observability/config/alloy/config.alloy
docker exec olympus-alloy alloy fmt /etc/alloy/config.alloy >/dev/null && echo "sintaxe ok"
docker restart olympus-alloy
```

Depois confira em `http://<host>:12345` (UI do Alloy) se os quatro componentes `prometheus.scrape.argos_*` estão saudáveis.

## Métricas renomeadas (painéis do Grafana)

O antigo producer virou o coletor, e as métricas mudaram de nome e de rótulo (`collector` virou `event_type`):

| Antes | Agora |
|---|---|
| `datalake_producer_cycles_total{status}` | `argos_collector_cycles_total{status}` |
| `datalake_pages_collected_total{collector}` | `argos_collector_pages_collected_total{event_type}` |
| `datalake_pages_queued_total{collector}` | `argos_collector_batches_sent_total{event_type,result}` (`accepted`, `duplicate`, `rejected`) |
| `datalake_collection_duration_seconds{collector}` | `argos_collector_collection_duration_seconds{event_type}` |
| `datalake_last_success_timestamp_seconds{collector}` | `argos_collector_last_success_timestamp_seconds{event_type}` |
| `datalake_pagination_stops_total{collector,reason}` | `argos_collector_pagination_stops_total{event_type,reason}` |
| `aruba_requests_total`, `aruba_request_errors_total`, `aruba_request_duration_seconds` | sem mudança |

Fila (`datalake_queue_*`): os nomes continuam, mas os valores do rótulo `status` em `datalake_queue_messages` agora são `PENDING`, `PROCESSING` e `DEAD` (não há mais `FAILED` nem `PROCESSED`; mensagens concluídas saem da fila). `datalake_queue_backlog` e `datalake_queue_oldest_pending_age_seconds` seguem iguais.

Worker (`datalake_messages_total`, `datalake_items_processed_total`, `datalake_records_written_total`, `datalake_processing_duration_seconds`, `datalake_stale_messages_recovered_total`): sem mudança. O rótulo `status` de `datalake_messages_total` agora pode ser `processed`, `failed` (será retentada) ou `dead`.

Novas, da Ingest API:

- `argos_ingest_requests_total{event_type,result}`: `accepted`, `duplicate`, `invalid`, `unknown_schema`, `forbidden`, `too_large`
- `argos_ingest_items_total{event_type}`
- `argos_ingest_request_duration_seconds{event_type}`

### Consultas úteis

```promql
# itens aceitos por tipo (por minuto)
sum by (event_type) (rate(argos_ingest_items_total[5m])) * 60

# lotes recusados na ingestão (algum coletor enviando fora do contrato)
sum by (event_type, result) (rate(argos_ingest_requests_total{result=~"invalid|unknown_schema|forbidden|too_large"}[5m]))

# fila acumulando
datalake_queue_backlog

# coletor sem sucesso há mais de 30 minutos
time() - argos_collector_last_success_timestamp_seconds > 1800

# mensagens mortas (dead-letter)
datalake_queue_messages{status="DEAD"}
```

## Profiling

O Pyroscope só inicializa com `pyroscope-io 0.8.11` a partir da correção de 24/10/2026 (argumentos `cpu_enabled`/`mem_enabled` removidos). A biblioteca não tem perfil de memória, então `PYROSCOPE_MEMORY_ENABLED` não tem mais efeito.
