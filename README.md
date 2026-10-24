# Argos — plataforma de eventos

O **Argos** recebe eventos de qualquer fonte, valida contra um contrato, enfileira, processa de forma assíncrona e guarda em um armazenamento analítico. A plataforma não conhece nenhuma fonte específica: quem busca os dados são **coletores**, que podem ser escritos em qualquer linguagem e só precisam falar HTTP com a Ingest API.

```text
coletor A ─┐
coletor B ─┼─ POST /v1/events ─> Ingest API ─> Redis Streams ─> worker ─> ClickHouse
coletor C ─┘   (API key)        (valida)       (fila durável)  (mapeia)   events / entity_latest
                                                                                   │
                                  navegador ─> web (nginx) ─> Query API ───────────┘
```

## Componentes

| Componente | Papel |
|---|---|
| **Ingest API** (`app/ingest`) | Autentica por API key, valida cada item contra o JSON Schema do `event_type` e responde `202` depois de gravar na fila. |
| **Fila** (Redis Streams) | Entrega durável com consumer group, retomada de mensagens presas, retries e dead-letter. |
| **Worker** (`app/worker.py`) | Lê a fila, extrai os campos canônicos usando o mapeamento do schema e grava no ClickHouse. |
| **ClickHouse** | `events` (histórico, buckets de 10 min) e `entity_latest` (estado atual), isolados por `tenant_id` e `source`. |
| **Query API** (`app/query`) | Consulta entidades, eventos e catálogo (`/v1/meta`), com filtros por dimensão, paginação por cursor e exportação (CSV, JSON Lines, XLSX, Parquet). Exige API key com papel `reader`. |
| **Web** (`web/`) | Interface React para explorar e exportar os dados (entidades, eventos, detalhe, exportações, fontes e fila). |
| **Coletores** (`collectors/`) | Programas independentes que fazem o pull e enviam. `collectors/aruba` é a referência. |

## Agnóstico por construção

- O envelope do evento é fixo (`source`, `event_type`, `schema_version`, `items`...). O conteúdo dos itens é livre.
- Cada `event_type` tem um **schema** que valida os itens e declara em `x-argos` onde estão o id, o nome, o status e as dimensões. Nada disso está no código da plataforma.
- Todo item completo é guardado em `payload`; as colunas extraídas são genéricas (`name`, `status`, `dimensions`).
- Um tipo novo é só um arquivo `<tipo>.v1.json` (em Kubernetes, um ConfigMap). Veja [`docs/ingest-contract.md`](docs/ingest-contract.md).

## Subindo

```bash
cp .env.example .env
cp collectors/aruba/.env.example collectors/aruba/.env   # preencha as credenciais da Aruba
./deploy.sh
```

Crie a chave do coletor e coloque em `ARGOS_API_KEY` no `collectors/aruba/.env` (as chaves têm papel: `collector` envia eventos, `reader` consulta, `admin` faz tudo):

```bash
docker compose exec ingest python -m app.ingest.keys create --name aruba --tenant default
docker compose up -d --force-recreate collector-aruba
```

Crie uma chave de leitura para entrar na interface (http://localhost:8090):

```bash
docker compose exec ingest python -m app.ingest.keys create --name ana --tenant default --role reader
```

Teste rápido com o schema `generic`:

```bash
curl -X POST http://localhost:8000/v1/events \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"source":"meu-sistema","event_type":"generic","items":[{"id":"1","name":"teste","status":"ok"}]}'
```

## Testes

```bash
pip install -r requirements-query.txt pytest httpx fakeredis
pytest

cd web && npm ci && npm test && npm run build
```

## Observabilidade

- Ingest API: `:8000/metrics` (`argos_ingest_*`). Query API: `:8001/metrics`.
- Worker: `:9102/metrics` (`datalake_*`, fila e processamento).
- Coletor Aruba: `:9101/metrics`.
- Traces via OTLP e perfis via Pyroscope, como antes.

## Documentação

- [Contrato de ingestão](docs/ingest-contract.md)
- [Armazenamento no ClickHouse](docs/clickhouse.md)
- [Query API e interface web](docs/query-and-web.md)
