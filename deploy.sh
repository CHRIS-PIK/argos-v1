#!/usr/bin/env bash
set -Eeuo pipefail

echo "==========================================="
echo "        ARGOS DEPLOY"
echo "==========================================="
echo

# Verifica se estamos na raiz do projeto
if [ ! -f docker-compose.yml ]; then
    echo "[ERRO] docker-compose.yml não encontrado."
    echo "Execute este script na raiz do projeto."
    exit 1
fi

echo "[1/7] Validando Docker..."
docker info >/dev/null

echo "[2/7] Validando docker-compose..."
docker compose config --quiet

echo "[3/7] Buildando imagens..."
COMPOSE_PARALLEL_LIMIT=1 docker compose build --pull ingest
COMPOSE_PARALLEL_LIMIT=1 docker compose build worker
COMPOSE_PARALLEL_LIMIT=1 docker compose build query
COMPOSE_PARALLEL_LIMIT=1 docker compose build collector-aruba

echo
echo "[4/7] Subindo Redis e ClickHouse..."
docker compose up -d redis clickhouse

echo
echo "Aguardando Redis e ClickHouse ficarem saudáveis..."

for container in argos-redis argos-clickhouse; do
    until [ "$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null)" = "healthy" ]; do
        printf "."
        sleep 2
    done
done

echo
echo "Redis e ClickHouse prontos."

echo
echo "[5/7] Subindo Ingest API, Worker e Coletor Aruba..."
docker compose up -d ingest query worker collector-aruba

echo
echo "[6/7] Status da stack"
docker compose ps

echo
echo "[7/7] Validando endpoints de métricas..."

sleep 5

echo
echo "Ingest API:"
curl -fs http://localhost:8000/healthz >/dev/null \
    && echo "OK" \
    || echo "Falhou"

echo "Query API:"
curl -fs http://localhost:8001/healthz >/dev/null \
    && echo "OK" \
    || echo "Falhou"

echo "Worker:"
curl -fs http://localhost:9102/metrics >/dev/null \
    && echo "OK" \
    || echo "Falhou"

echo
echo "==========================================="
echo " Stack iniciada!"
echo "==========================================="

echo
echo "Containers:"
docker compose ps

echo
echo "Logs em tempo real:"
echo "docker compose logs -f ingest query worker collector-aruba"
