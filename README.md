# Argos — Data Ingestion Platform

O Argos é uma plataforma de ingestão e telemetria de infraestrutura. Atualmente, ele coleta dados da Aruba New Central, aplica autenticação, paginação segura, deduplicação e persistência durável, processa os payloads de forma assíncrona e disponibiliza dados normalizados, históricos e snapshots para consumo por relatórios, dashboards e integrações futuras.

O projeto deixou de ser apenas um piloto de extração para Power BI. Hoje ele opera como uma esteira observável e resiliente, formada por `producer`, fila persistente em MariaDB, `worker`, modelos relacionais e instrumentação Prometheus.

## Arquitetura

```text
Aruba New Central API
        |
        v
producer (Python)
  - OAuth2 / refresh token
  - paginação
  - retry e backoff
  - deduplicação por hash
  - métricas Prometheus :9101
        |
        v
ingestion_queue (MariaDB)
  PENDING -> PROCESSING -> PROCESSED
                  |            |
                  +-> FAILED -> DEAD
        |
        v
worker (Python)
  - claim concorrente com SKIP LOCKED
  - normalização
  - UPSERT idempotente
  - histórico e snapshot
  - recuperação de locks expirados
  - métricas Prometheus :9102
        |
        +--> tabelas current
        +--> tabelas históricas de 10 minutos
        +--> raw_entity_current
        +--> raw_entity_snapshot_10m
        +--> views de consumo

Métricas da aplicação
        |
        v
Grafana Alloy -> Mimir -> Grafana
```

Mais detalhes sobre a fila e as garantias de processamento estão em [`ASYNC_ARCHITECTURE.md`](ASYNC_ARCHITECTURE.md).

## Stack

- Python 3.12
- MariaDB 11.4
- Docker Compose
- Requests e SQLAlchemy
- Prometheus Client
- Grafana Alloy
- Grafana Mimir
- Grafana 12.3.1
- Loki, Tempo e Pyroscope disponíveis no homelab para evolução da observabilidade

## Coletores atuais

- APs: `network-monitoring/v1/aps`
- Clientes: `network-monitoring/v1/clients`
- Switches: `network-monitoring/v1/switches`
- Rádios: `network-monitoring/v1/radios`
- Alertas: `network-notifications/v1/alerts`
- Licenças
- IA Insights

Os coletores são independentes e possuem limites de paginação, detecção de payload repetido e proteção contra loops infinitos.

## Modelagem de dados

### Estado atual

- `ap_current`
- `client_current`
- `switch_current`
- `radio_current`
- `alert_current`
- `license_current`
- `insight_current`
- `raw_entity_current`

Essas tabelas mantêm o snapshot mais recente de cada entidade por meio de `UPSERT`.

### Histórico

- `ap_metrics_10m`
- `client_summary_10m`
- `raw_entity_snapshot_10m`

Os históricos são gravados em buckets de 10 minutos para evitar duplicação dentro da mesma janela.

### Fila e auditoria

- `ingestion_queue`
- `ingestion_runs`
- `vw_ingestion_queue_health`

### Views de consumo

- `vw_ap_latest`
- `vw_client_latest`
- `vw_client_summary`
- `vw_switch_latest`
- `vw_radio_latest`
- `vw_alerts`
- `vw_licenses`
- `vw_ai_insights`
- `vw_raw_entity_latest`

Para consumidores externos, prefira as views em vez das tabelas físicas.

## Configuração

```bash
cp .env.example .env
nano .env
```

As principais variáveis incluem:

- credenciais OAuth da Aruba
- URL base da API
- conexão MariaDB
- intervalos de coleta
- limites de paginação
- tentativas e backoff
- portas de métricas do producer e worker
- intervalo de atualização das métricas da fila

Nunca versione o arquivo `.env`.

## Subida do ambiente

```bash
docker compose up -d --build
```

Em hosts com pouca memória, evite builds paralelos:

```bash
COMPOSE_PARALLEL_LIMIT=1 docker compose build producer
COMPOSE_PARALLEL_LIMIT=1 docker compose build worker
docker compose up -d --force-recreate producer worker
```

Acompanhar a aplicação:

```bash
docker compose ps
docker compose logs -f producer worker
```

## Validação rápida

### Containers

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Métricas

```bash
curl -s http://localhost:9101/metrics | grep -E 'datalake_|aruba_' | head -80
curl -s http://localhost:9102/metrics | grep -E 'datalake_' | head -80
```

Consultas úteis no Grafana/Mimir:

```promql
up{job=~"datalake-producer|datalake-worker"}
```

```promql
datalake_queue_backlog
```

```promql
histogram_quantile(
  0.95,
  sum by (le, collector) (
    rate(datalake_processing_duration_seconds_bucket[5m])
  )
)
```

## Validação no banco

Listar tabelas:

```bash
docker exec -it aruba-mariadb \
  mariadb -u root -p aruba_reporting \
  -e "SHOW TABLES;"
```

Estrutura e amostra de APs:

```bash
docker exec -it aruba-mariadb \
  mariadb -u root -p aruba_reporting \
  -e "DESC ap_current; SELECT * FROM vw_ap_latest LIMIT 10;"
```

Saúde da fila:

```bash
docker exec -it aruba-mariadb \
  mariadb -u root -p aruba_reporting \
  -e "SELECT * FROM vw_ingestion_queue_health;"
```

Mensagens mortas:

```bash
docker exec -it aruba-mariadb \
  mariadb -u root -p aruba_reporting \
  -e "
SELECT id, collector_name, endpoint, attempts, error_message, created_at
FROM ingestion_queue
WHERE status = 'DEAD'
ORDER BY id DESC;
"
```

## Garantias da esteira

- cada página válida é persistida antes do processamento;
- deduplicação por coletor, endpoint, bucket, página e hash do payload;
- processamento `at least once`;
- escritas finais idempotentes por `UPSERT`;
- claim concorrente com `FOR UPDATE SKIP LOCKED`;
- retry com backoff exponencial;
- transição de falhas para `FAILED` e, após o limite, para `DEAD`;
- recuperação automática de mensagens presas em `PROCESSING`;
- detecção de payload repetido e limite máximo de páginas por coleta;
- preservação do JSON bruto para auditoria e evolução dos modelos.

## Observabilidade

O producer expõe métricas em `:9101` e o worker em `:9102`.

Entre as métricas disponíveis:

- ciclos do producer por status;
- páginas coletadas e enfileiradas por collector;
- duração das coletas;
- timestamp da última coleta bem-sucedida;
- interrupções preventivas de paginação;
- requisições, erros e latência da API Aruba;
- mensagens processadas por status;
- itens processados e registros escritos;
- duração do processamento;
- quantidade de mensagens por estado da fila;
- backlog e idade do item pendente mais antigo;
- recuperação de locks expirados.

A coleta Prometheus é feita pelo Grafana Alloy, com armazenamento no Mimir e visualização no Grafana.

## Consumo por Power BI e outros clientes

Crie um usuário somente leitura e restrinja o consumo às views:

```sql
CREATE USER 'reporting_reader'@'%' IDENTIFIED BY 'troque_esta_senha';
GRANT SELECT ON aruba_reporting.* TO 'reporting_reader'@'%';
FLUSH PRIVILEGES;
```

Não use o usuário da aplicação em ferramentas externas.

## Operação e evolução

Próximas evoluções naturais:

- logs estruturados em JSON e envio ao Loki;
- tracing com OpenTelemetry e Tempo;
- profiling contínuo com Pyroscope;
- alertas de disponibilidade, backlog, freshness e erro HTTP;
- novos conectores para outras plataformas de infraestrutura;
- camada de API de consulta para consumidores externos.

## Definição do projeto

A definição mais adequada atualmente é:

> **Argos é uma Infrastructure Telemetry & Data Ingestion Platform**, criada para coletar, normalizar, persistir e observar dados operacionais de plataformas de infraestrutura de forma resiliente e extensível.
