# Arquitetura assíncrona e durável

O fluxo foi separado em dois serviços:

```text
Aruba New Central
      |
      v
producer
      |
      v
ingestion_queue (MariaDB)
      |
      v
worker(s)
      |
      v
tabelas normalizadas + raw_entity_current + raw_entity_snapshot_10m
```

## Garantias

- Cada página recebida da API é persistida antes do processamento.
- A fila usa deduplicação por endpoint, bucket, página e hash do payload.
- O processamento é `at least once`.
- As escritas finais usam `UPSERT`, tornando o reprocessamento idempotente.
- Mensagens com falha usam backoff exponencial.
- Depois do limite de tentativas, a mensagem vai para `DEAD`.
- Mensagens presas em `PROCESSING` são recuperadas automaticamente.

## Aplicar a migration em banco já existente

```bash
set -a
source .env
set +a

docker exec -i aruba-mariadb mariadb \
  -uroot -p"$DB_ROOT_PASSWORD" "$DB_NAME" \
  < sql/003_durable_queue.sql
```

## Subir

```bash
docker compose down
docker compose up -d --build --scale worker=2
docker compose logs -f producer worker
```

## Saúde da fila

```sql
SELECT * FROM vw_ingestion_queue_health;
```

Mensagens mortas:

```sql
SELECT id, collector_name, endpoint, attempts, error_message, created_at
FROM ingestion_queue
WHERE status = 'DEAD'
ORDER BY id DESC;
```

Reprocessar uma mensagem morta:

```sql
UPDATE ingestion_queue
SET status='PENDING',
    attempts=0,
    available_at=NOW(6),
    error_message=NULL
WHERE id=<ID>;
```

APs e clientes continuam sendo normalizados nas tabelas originais. Os demais endpoints também são preservados nas tabelas genéricas `raw_entity_*`, evitando descarte de dados enquanto os modelos específicos são refinados.
