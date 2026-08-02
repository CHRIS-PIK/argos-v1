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
COMPOSE_PARALLEL_LIMIT=1 docker compose build --pull producer
COMPOSE_PARALLEL_LIMIT=1 docker compose build worker

echo
echo "[4/7] Subindo MariaDB..."
docker compose up -d mariadb

echo
echo "Aguardando MariaDB ficar saudável..."

until [ "$(docker inspect -f '{{.State.Health.Status}}' aruba-mariadb 2>/dev/null)" = "healthy" ]; do
    printf "."
    sleep 2
done

echo
echo "MariaDB pronto."

echo
echo "[5/7] Subindo Producer e Worker..."
docker compose up -d producer worker

echo
echo "[6/7] Status da stack"
docker compose ps

echo
echo "[7/7] Validando endpoints de métricas..."

sleep 5

echo
echo "Producer:"
curl -fs http://localhost:9101/metrics >/dev/null \
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
echo "docker compose logs -f producer worker"
