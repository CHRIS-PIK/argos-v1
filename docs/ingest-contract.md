# Contrato de ingestão

A plataforma não coleta dados. Ela recebe lotes de eventos de **coletores** pela Ingest API, valida contra um schema registrado, persiste na fila e o worker processa como antes.

```text
coletor (qualquer linguagem) --POST /v1/events--> ingest --> ingestion_queue --> worker --> storage
```

## Autenticação

Cada coletor usa uma API key no header `X-API-Key`. A chave pertence a um `tenant_id` e pode ser restrita a alguns `event_type`.

```bash
docker compose exec ingest python -m app.ingest.keys create --name aruba --tenant default --event-types aps,clients,switches,radios,alerts
docker compose exec ingest python -m app.ingest.keys revoke --name aruba
```

O valor da chave é exibido uma única vez; no banco fica só o hash SHA-256.

## `POST /v1/events`

```json
{
  "source": "aruba-central",
  "event_type": "aps",
  "schema_version": "1",
  "batch_id": "id-unico-do-lote",
  "page": 1,
  "collected_at": "2026-10-24T19:40:00Z",
  "items": [{ "id": "ap-1", "status": "Up" }]
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

`202` significa que o lote está **persistido na fila**; o processamento é assíncrono. Falhas no worker não voltam ao coletor: ficam em `FAILED`/`DEAD` na fila.

## Schemas

Ficam em `app/ingest/schemas/<event_type>.v<N>.json` (JSON Schema 2020-12) e validam **cada item**. O diretório pode ser trocado por `SCHEMAS_DIR`, por exemplo montando um ConfigMap no Kubernetes. Para criar um tipo novo, adicione o arquivo e reinicie a Ingest API.

`GET /v1/schemas` (com API key) lista os tipos e versões aceitos.

Os schemas iniciais exigem que o item tenha ao menos um identificador reconhecido pelo worker (`id`, `serialNumber`, `clientId`, `macAddress`, `mac`, `subscriptionId`, `insightId` ou `alertId`). Os campos restantes são livres.

Como o worker trata cada tipo:

- `aps`, `clients`, `switches`, `alerts`: tabelas normalizadas atuais e históricos, além do bruto.
- `radios`: tabela `radio_current`, além do bruto.
- qualquer outro tipo, incluindo `generic`: apenas `raw_entity_current` e `raw_entity_snapshot_10m`.

## Limitações conhecidas

- `raw_entity_current` tem chave `(collector_name, entity_id)`: duas `source` diferentes enviando o mesmo `event_type` e o mesmo id sobrescrevem uma à outra. Isso desaparece com o novo armazenamento (fase 2); até lá, use `event_type` distintos por source.
- `tenant_id` é gravado na fila, mas o worker ainda não o propaga para as tabelas de destino.

## Coletores

O coletor Aruba está em [`collectors/aruba`](../collectors/aruba). Ele é independente da plataforma (imagem, dependências e `.env` próprios) e só fala HTTP com a Ingest API. Use-o como referência para novos coletores.

## Migração

Aplique `sql/008_ingest_contract.sql` em bancos existentes (o init do Docker só roda em volume novo):

```bash
docker compose exec -T mariadb sh -c 'mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE"' < sql/008_ingest_contract.sql
```
