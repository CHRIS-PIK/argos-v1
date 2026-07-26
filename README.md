# Argos — Infrastructure Telemetry & Data Ingestion Platform

O **Argos** é uma plataforma de ingestão de dados operacionais orientada a APIs. Ele coleta, normaliza, persiste e disponibiliza informações de infraestrutura de forma assíncrona, resiliente e observável.

A implementação atual integra a API do **HPE Aruba Networking Central**, mas a arquitetura foi construída para permitir a inclusão de novos coletores e novas fontes de dados sem alterar o fluxo principal da aplicação.

Hoje o Argos combina:

- coleta concorrente e paginada;
- autenticação OAuth2 com renovação de token;
- fila persistente em MariaDB;
- processamento assíncrono e idempotente;
- snapshots atuais e históricos;
- métricas, logs, traces e profiling contínuo;
- dados preparados para consumo por Power BI, Grafana e outras integrações.

## Visão geral da arquitetura

```text
                         HPE Aruba Central API
                                  |
                                  v
                         producer (Python)
                  OAuth2 | paginação | retry
                                  |
                                  v
                       ingestion_queue (MariaDB)
                  PENDING -> PROCESSING -> PROCESSED
                               |          |
                               +-> FAILED -> DEAD
                                  |
                                  v
                          worker (Python)
                normalização | UPSERT | histórico
                                  |
              +-------------------+-------------------+
              |                   |                   |
              v                   v                   v
        tabelas current     históricos de 10m    dados brutos
              |                   |                   |
              +-------------------+-------------------+
                                  |
                                  v
                      Views / Power BI / Relatórios
```

A fila desacopla a coleta do processamento. O producer pode continuar coletando páginas enquanto o worker processa os payloads no ritmo suportado pelo banco.

Mais detalhes sobre concorrência, retries e garantias de entrega estão em [`ASYNC_ARCHITECTURE.md`](ASYNC_ARCHITECTURE.md).

## Arquitetura de observabilidade

O Argos produz os quatro principais sinais de observabilidade:

```text
                        producer / worker
                               |
          +--------------------+--------------------+
          |                    |                    |
          v                    v                    v
       Metrics               Logs                Traces
     Prometheus            Docker stdout       OpenTelemetry
          |                    |                    |
          +--------------------+--------------------+
                               |
                               v
                         Grafana Alloy
                    |          |          |
                    v          v          v
                  Mimir       Loki       Tempo
                    \          |          /
                     \         |         /
                      +------ Grafana ---+

                        producer / worker
                               |
                               v
                       Pyroscope SDK
                               |
                               v
                         Pyroscope
                               |
                               v
                            Grafana
```

Essa separação mantém a aplicação desacoplada dos backends. O Argos expõe métricas Prometheus, escreve logs em `stdout`, envia traces via OTLP e perfis pelo SDK do Pyroscope.

## Stack

- Python 3.12
- MariaDB 11.4
- Docker Compose
- Requests
- Prometheus Client
- OpenTelemetry
- Grafana Alloy
- Grafana Mimir
- Grafana Loki
- Grafana Tempo
- Grafana Pyroscope
- Grafana

## Serviços da aplicação

### Producer

Responsável por:

- autenticar na API de origem;
- renovar tokens quando necessário;
- percorrer endpoints paginados;
- aplicar retry e backoff;
- detectar payloads repetidos;
- limitar páginas por execução;
- enfileirar cada página válida;
- expor métricas em `:9101`;
- emitir traces de ciclos e coletores;
- enviar perfis de CPU e memória.

### Worker

Responsável por:

- buscar mensagens da fila com `FOR UPDATE SKIP LOCKED`;
- transformar e normalizar payloads;
- gravar dados atuais e históricos;
- executar UPSERTs idempotentes;
- marcar mensagens como processadas ou falhas;
- recuperar mensagens presas em processamento;
- expor métricas em `:9102`;
- emitir traces de processamento;
- enviar perfis de CPU e memória.

### MariaDB

Armazena:

- fila persistente de ingestão;
- estado atual das entidades;
- históricos em buckets de 10 minutos;
- payloads brutos para auditoria;
- views para consumidores externos.

## Coletores ativos

| Coletor | Endpoint |
|---|---|
| APs | `network-monitoring/v1/aps` |
| Clientes | `network-monitoring/v1/clients` |
| Switches | `network-monitoring/v1/switches` |
| Rádios | `network-monitoring/v1/radios` |
| Alertas | `network-notifications/v1/alerts` |

Licenças e AI Insights permanecem desabilitados até que os endpoints correspondentes sejam validados para o tenant e solicitados pelo cliente.

Todos os coletores usam o mesmo pipeline:

```text
endpoint -> paginação -> enqueue_page -> ingestion_queue
         -> claim_message -> process_message -> banco
```

## Modelagem de dados

### Estado atual

- `ap_current`
- `client_current`
- `switch_current`
- `radio_current`
- `alert_current`
- `raw_entity_current`

Essas tabelas mantêm o estado mais recente de cada entidade por meio de `UPSERT`.

### Histórico

- `ap_metrics_10m`
- `client_summary_10m`
- `raw_entity_snapshot_10m`

Os registros históricos são agrupados em buckets de 10 minutos para evitar duplicações dentro da mesma janela.

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
- `vw_raw_entity_latest`

Consumidores externos devem preferir as views em vez das tabelas físicas.

## Como adicionar um novo collector

Um novo collector precisa participar de quatro etapas:

```text
1. declarar endpoint
2. coletar e enfileirar
3. processar o payload
4. persistir e observar
```

### 1. Definir um nome estável

Escolha um identificador curto, em minúsculas e no plural.

Exemplo:

```text
sites
```

Esse nome será usado em:

- métricas;
- logs;
- spans;
- fila;
- tabela bruta;
- funções de processamento.

Evite renomeá-lo depois que dados já tiverem sido persistidos.

### 2. Registrar o endpoint no producer

Edite `app/producer.py` e adicione o collector ao dicionário `STATIC_ENDPOINTS`:

```python
STATIC_ENDPOINTS = {
    "aps": "network-monitoring/v1/aps",
    "clients": "network-monitoring/v1/clients",
    "switches": "network-monitoring/v1/switches",
    "radios": "network-monitoring/v1/radios",
    "alerts": "network-notifications/v1/alerts",
    "sites": "network-monitoring/v1/sites",
}
```

A partir disso, o producer passa automaticamente a:

- chamar o endpoint;
- aplicar paginação;
- aplicar retry;
- detectar páginas repetidas;
- limitar o número máximo de páginas;
- calcular hash do payload;
- gravar cada página na fila;
- emitir métricas e traces do collector.

### 3. Validar o formato de paginação

O cliente HTTP está em `app/api.py`.

Antes de concluir a implementação, valide se o novo endpoint retorna uma destas estruturas:

```json
{
  "items": [],
  "next": "cursor"
}
```

```json
{
  "body": {
    "items": [],
    "next": "cursor"
  }
}
```

```json
{
  "items": [],
  "offset": 0,
  "total": 100
}
```

Caso o endpoint use outro padrão, ajuste `ArubaClient.pages()` com cuidado para não quebrar os coletores existentes.

Confirme também:

- campo que identifica a próxima página;
- tamanho máximo de página;
- comportamento quando a última página é vazia;
- resposta quando o token expira;
- possíveis limites de rate limit.

### 4. Garantir um identificador de entidade

Todo item precisa possuir um identificador estável.

A função `entity_id()` em `app/processors.py` tenta localizar atualmente:

```python
id
serialNumber
clientId
macAddress
mac
subscriptionId
insightId
alertId
```

Caso o novo payload use outro campo, inclua-o na função:

```python
def entity_id(item):
    return str(
        first(
            item,
            "id",
            "serialNumber",
            "siteId",
            default="",
        ) or ""
    )
```

Sem um ID estável, o item será ignorado pelo processamento bruto.

### 5. Escolher o tipo de persistência

Existem três caminhos.

#### Opção A — somente armazenamento bruto

Nenhuma função especializada é obrigatória.

O `process_raw()` já grava automaticamente o collector em:

- `raw_entity_current`;
- `raw_entity_snapshot_10m`.

Esse é o caminho recomendado para um primeiro piloto.

#### Opção B — tabela especializada simples

Para uma tabela que preserve principalmente o JSON bruto, crie a tabela no diretório `sql/` e registre o collector em `SPECIALIZED_RAW_TABLES`:

```python
SPECIALIZED_RAW_TABLES = {
    "switches": "switch_current",
    "radios": "radio_current",
    "alerts": "alert_current",
    "sites": "site_current",
}
```

A tabela precisa aceitar a estrutura usada por `process_specialized_raw()`:

```sql
entity_id
collected_at
updated_at
raw_json
```

#### Opção C — modelo relacional completo

Quando o payload precisa de colunas próprias, filtros, agregações ou histórico dedicado:

1. crie as tabelas e views em `sql/`;
2. crie as instruções SQL em `app/processors.py`;
3. implemente uma função `process_<collector>()`;
4. registre a função em `process_message()`.

Exemplo:

```python
def process_sites(items, collected_at, bucket_at):
    rows = []

    for site in items:
        site_id = entity_id(site)
        if not site_id:
            continue

        rows.append(
            (
                site_id,
                site.get("siteName"),
                site.get("status"),
                collected_at,
            )
        )

    with connection() as cnx:
        cur = cnx.cursor()
        cur.executemany(SITE_CURRENT_SQL, rows)

    return len(rows)
```

Depois, registre no roteamento:

```python
def process_message(collector_name, items, collected_at, bucket_at):
    written = process_raw(collector_name, items, collected_at, bucket_at)

    if collector_name == "aps":
        written += process_aps(items, collected_at, bucket_at)
    elif collector_name == "clients":
        written += process_clients(items, collected_at, bucket_at)
    elif collector_name == "sites":
        written += process_sites(items, collected_at, bucket_at)
    elif collector_name in SPECIALIZED_RAW_TABLES:
        written += process_specialized_raw(
            collector_name,
            items,
            collected_at,
        )

    return written
```

### 6. Criar ou atualizar views

Caso os dados sejam consumidos por Power BI ou outra integração, crie uma view estável:

```sql
CREATE OR REPLACE VIEW vw_site_latest AS
SELECT
    site_id,
    site_name,
    status,
    collected_at
FROM site_current;
```

Evite acoplar consumidores externos diretamente às tabelas internas.

### 7. Instrumentar o collector

Os coletores registrados em `STATIC_ENDPOINTS` já recebem automaticamente:

- contador de páginas coletadas;
- contador de páginas enfileiradas;
- duração da coleta;
- timestamp da última coleta bem-sucedida;
- erros HTTP;
- interrupções de paginação;
- span de coleta no Tempo.

Ao criar lógica adicional, adicione atributos úteis ao span, sem incluir credenciais ou payloads completos.

Exemplos de atributos seguros:

```text
argos.collector=sites
argos.page_number=2
argos.items_count=100
http.route=network-monitoring/v1/sites
```

Nunca envie para logs, métricas ou traces:

- access tokens;
- refresh tokens;
- client secrets;
- senhas;
- payloads contendo dados sensíveis.

### 8. Testar localmente

Suba os serviços:

```bash
docker compose up -d --build producer worker
```

Verifique os logs:

```bash
docker compose logs -f producer worker
```

Confirme que o collector enfileirou mensagens:

```sql
SELECT
    id,
    collector_name,
    status,
    attempts,
    created_at
FROM ingestion_queue
WHERE collector_name = 'sites'
ORDER BY id DESC
LIMIT 20;
```

Confirme a persistência bruta:

```sql
SELECT
    collector_name,
    entity_id,
    entity_name,
    status,
    updated_at
FROM raw_entity_current
WHERE collector_name = 'sites'
LIMIT 20;
```

Valide também:

- paginação completa;
- ausência de payload repetido;
- recuperação após erro HTTP;
- idempotência ao processar a mesma página novamente;
- atualização do snapshot atual;
- criação correta do histórico;
- métricas em `:9101` e `:9102`;
- traces no Tempo;
- perfis no Pyroscope;
- logs no Loki.

### Checklist de novo collector

- [ ] nome estável definido;
- [ ] endpoint registrado em `STATIC_ENDPOINTS`;
- [ ] paginação validada;
- [ ] identificador estável reconhecido por `entity_id()`;
- [ ] persistência bruta validada;
- [ ] tabela especializada criada, quando necessária;
- [ ] função de processamento registrada, quando necessária;
- [ ] view de consumo criada, quando necessária;
- [ ] collector visível nas métricas;
- [ ] collector visível nos logs;
- [ ] collector visível nos traces;
- [ ] idempotência testada;
- [ ] credenciais e dados sensíveis não expostos.

## Configuração

Crie o arquivo de ambiente:

```bash
cp .env.example .env
nano .env
```

As principais variáveis incluem:

- credenciais OAuth da Aruba;
- URL base da API;
- conexão MariaDB;
- intervalo de coleta;
- concorrência do producer;
- limites de paginação;
- política de retry;
- portas de métricas;
- configuração OTLP;
- endereço do Pyroscope;
- identificação do ambiente e host.

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

Acompanhe a aplicação:

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
curl -s http://localhost:9101/metrics \
  | grep -E 'datalake_|aruba_' \
  | head -80

curl -s http://localhost:9102/metrics \
  | grep -E 'datalake_' \
  | head -80
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

### Logs no Loki

No Grafana Explore:

```logql
{application="argos"}
```

Exemplos de filtros:

```logql
{application="argos", service="producer"}
```

```logql
{application="argos"} |= "failed"
```

### Traces no Tempo

Procure pelos serviços:

```text
argos-producer
argos-worker
```

Spans esperados incluem ciclos do producer, coletas por endpoint e processamento de mensagens da fila.

### Perfis no Pyroscope

Procure pelas aplicações:

```text
argos.producer
argos.worker
```

Use perfis de CPU para identificar funções custosas e perfis de memória para investigar crescimento de alocação.

## Validação no banco

Listar tabelas:

```bash
docker exec -it aruba-mariadb \
  mariadb -u root -p aruba_reporting \
  -e "SHOW TABLES;"
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
- deduplicação por collector, endpoint, bucket, página e hash;
- processamento `at least once`;
- escritas finais idempotentes por `UPSERT`;
- claim concorrente com `FOR UPDATE SKIP LOCKED`;
- retry com backoff exponencial;
- transição de falhas para `FAILED` e depois `DEAD`;
- recuperação automática de mensagens presas em `PROCESSING`;
- proteção contra loops de paginação;
- preservação do JSON bruto para auditoria e evolução dos modelos.

## Observabilidade

### Métricas

O producer expõe métricas em `:9101` e o worker em `:9102`.

Entre os indicadores disponíveis:

- ciclos do producer por status;
- páginas coletadas e enfileiradas;
- duração das coletas;
- última coleta bem-sucedida;
- interrupções preventivas de paginação;
- requisições, erros e latência da API;
- mensagens processadas por status;
- itens processados e registros escritos;
- duração do processamento;
- backlog e idade da mensagem pendente mais antiga;
- mensagens por estado da fila;
- recuperação de locks expirados.

### Logs

Os serviços escrevem em `stdout` e são coletados pelo Grafana Alloy para o Loki.

Os labels principais permitem filtrar por:

- aplicação;
- serviço;
- container;
- ambiente;
- host;
- projeto Docker Compose.

### Traces

OpenTelemetry instrumenta o producer e o worker.

Os traces permitem acompanhar:

- duração de um ciclo de coleta;
- tempo gasto por endpoint;
- chamadas HTTP externas;
- falhas e exceções;
- tempo de processamento de mensagens.

### Continuous profiling

O SDK do Pyroscope coleta perfis contínuos de CPU e memória dos serviços.

Isso permite investigar consumo elevado sem reproduzir o problema manualmente ou iniciar um profiler apenas após o incidente.

## Consumo por Power BI e outros clientes

Crie um usuário somente leitura e restrinja o consumo às views:

```sql
CREATE USER 'reporting_reader'@'%' IDENTIFIED BY 'troque_esta_senha';
GRANT SELECT ON aruba_reporting.* TO 'reporting_reader'@'%';
FLUSH PRIVILEGES;
```

Não use o usuário da aplicação em ferramentas externas.

## Possíveis evoluções

As próximas melhorias devem ser guiadas pela necessidade do cliente. Entre as possibilidades:

- logs estruturados em JSON;
- exemplars entre métricas e traces;
- correlação entre métricas, logs, traces e profiles;
- alertas de disponibilidade, backlog e freshness;
- feature flags para coletores;
- endpoint de health check;
- novos conectores para outras plataformas;
- API de consulta para consumidores externos;
- interface administrativa.

## Definição do projeto

> **Argos é uma Infrastructure Telemetry & Data Ingestion Platform criada para coletar, normalizar, persistir e observar dados operacionais de plataformas de infraestrutura de forma resiliente e extensível.**
