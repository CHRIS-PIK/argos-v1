# Contrato de ingestão

A plataforma não coleta dados. Ela recebe lotes de eventos de **coletores** pela Ingest API, valida contra um schema registrado, persiste na fila (Redis Streams) e o worker grava no ClickHouse.

```text
coletor (qualquer linguagem) --POST /v1/events--> ingest --> Redis Streams --> worker --> ClickHouse
```

## Autenticação

Cada coletor usa uma API key no header `X-API-Key`. A chave pertence a um `tenant_id` e pode ser restrita a alguns `event_type`. As chaves ficam no Redis (só o hash SHA-256).

```bash
docker compose exec ingest python -m app.ingest.keys create --name meu-coletor --tenant default --event-types generic
docker compose exec ingest python -m app.ingest.keys revoke --name meu-coletor
```

O valor da chave é exibido uma única vez. Mudanças de revogação levam até 30 s para valer (cache da API).

## `POST /v1/events`

```json
{
  "source": "meu-sistema",
  "event_type": "generic",
  "schema_version": "1",
  "batch_id": "id-unico-do-lote",
  "page": 1,
  "collected_at": "2026-10-24T19:40:00Z",
  "items": [{ "id": "1", "name": "pedido 1", "status": "open" }]
}
```

| Campo | Obrigatório | Descrição |
|---|---|---|
| `source` | sim | Sistema de origem. Minúsculas, números, `.`, `_`, `-` (até 64). |
| `event_type` | sim | Tipo do evento. Precisa ter schema registrado. |
| `schema_version` | não (`"1"`) | Versão do schema do `event_type`. |
| `batch_id` | não | Chave de idempotência. Reenviar o mesmo `batch_id` + `page` não duplica. Sem ele, a dedup usa o hash do conteúdo + bucket de 10 min. |
| `page` | não (`1`) | Página dentro do lote lógico. |
| `collected_at` | não (agora) | Quando o dado foi coletado. Rejeitado se estiver mais de 5 min no futuro ou mais de 24 h no passado (`INGEST_MAX_PAST_HOURS`). |
| `items` | sim | De 1 a `INGEST_MAX_ITEMS` (5000) objetos. |

### Respostas

| Status | Significado | O coletor deve |
|---|---|---|
| `202` | Aceito (`"duplicate": true` se já existia). | Seguir. |
| `401` | Chave ausente ou inválida. | Corrigir a configuração. |
| `403` | Chave sem permissão para esse `event_type`. | Corrigir a configuração. |
| `413` | Lote maior que o limite. | Dividir o lote. |
| `422` | Payload fora do contrato; `detail` lista os erros. | Corrigir o dado; não reenviar igual. |
| `429`, `5xx` | Falha temporária. | Reenviar com backoff, respeitando `Retry-After`. |

`202` significa que o lote está **persistido na fila**; o processamento é assíncrono. Falhas no worker não voltam ao coletor: a mensagem é retentada e, esgotadas as tentativas, vai para a dead-letter (`argos:events:dead`).

## Schemas e mapeamento

Um tipo de evento é definido por um arquivo `<event_type>.v<N>.json` (JSON Schema 2020-12). O schema faz duas coisas:

1. **Valida cada item** (campos, tipos, obrigatórios).
2. **Declara o mapeamento** em `x-argos`: de onde tirar os campos canônicos que viram colunas.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["order_id"],
  "x-argos": {
    "entity_id": ["order_id"],
    "name": ["customer.name"],
    "status": ["state"],
    "dimensions": { "region": "shipping.region", "store": "store_code" }
  }
}
```

| Chave | Vira | Regra |
|---|---|---|
| `entity_id` | `entity_id` | Lista de caminhos; vale o primeiro preenchido. **Obrigatório**: item sem id é rejeitado com `422`. Padrão: `["id"]`. |
| `name` | `name` | Lista de caminhos (opcional). |
| `status` | `status` | Lista de caminhos (opcional). |
| `dimensions` | `dimensions` | Mapa `chave -> caminho`; só entram as que existirem no item. |

Caminhos aninhados usam ponto (`customer.name`). O item completo sempre fica em `payload`.

Onde ficam os schemas:

- `app/ingest/schemas/`: apenas o `generic` (qualquer objeto com `id`).
- Qualquer diretório listado em `SCHEMAS_DIR` (separado por `:` no Linux), buscado recursivamente. No compose, `collectors/aruba/schemas` é montado em `/schemas/aruba`. Em Kubernetes, use um ConfigMap.

Para criar um tipo novo, adicione o arquivo e reinicie a Ingest API e o worker. `GET /v1/schemas` (com API key) lista o que está registrado.

## Coletores

O coletor Aruba está em [`collectors/aruba`](../collectors/aruba) e traz seus próprios schemas. Ele é independente da plataforma (imagem, dependências e `.env` próprios) e só fala HTTP com a Ingest API. Use-o como referência para novos coletores.

## Limitações conhecidas

- `schema_version` novas exigem arquivo novo; não há migração automática entre versões.
- O ClickHouse recebe o payload bruto; não há tabelas colunares por tipo.
