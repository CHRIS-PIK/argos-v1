#!/usr/bin/env bash
set -e

echo "========================================="
echo " Instalação do Docker Engine Oficial"
echo "========================================="

# Verifica se é root
if [ "$EUID" -ne 0 ]; then
    echo "Execute com sudo:"
    echo "sudo bash install-docker.sh"
    exit 1
fi

echo "[1/7] Removendo versões antigas..."
apt remove -y \
    docker.io \
    docker-compose \
    docker-compose-v2 \
    docker-doc \
    podman-docker \
    containerd \
    runc || true

echo "[2/7] Atualizando repositórios..."
apt update

echo "[3/7] Instalando dependências..."
apt install -y \
    ca-certificates \
    curl \
    gnupg

echo "[4/7] Adicionando chave GPG..."
install -m 0755 -d /etc/apt/keyrings

curl -fsSL \
    https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
    -o /etc/apt/keyrings/docker.asc

chmod a+r /etc/apt/keyrings/docker.asc

echo "[5/7] Adicionando repositório oficial..."
echo \
"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
> /etc/apt/sources.list.d/docker.list

apt update

echo "[6/7] Instalando Docker..."
apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

echo "[7/7] Habilitando serviço..."
systemctl enable --now docker

# Adiciona o usuário que chamou o sudo ao grupo docker
if [ -n "$SUDO_USER" ]; then
    usermod -aG docker "$SUDO_USER"
    TARGET_USER="$SUDO_USER"
else
    TARGET_USER="$(logname 2>/dev/null || echo root)"
    usermod -aG docker "$TARGET_USER" || true
fi

echo
echo "========================================="
echo " Docker instalado com sucesso!"
echo "========================================="
echo
echo "Versões:"
docker --version
docker compose version
docker buildx version

echo
echo "Teste:"
docker run --rm hello-world

echo
echo "Usuário '$TARGET_USER' foi adicionado ao grupo docker."
echo "Faça logout/login ou execute:"
echo
echo "newgrp docker"
echo
echo "Pronto para buildar o Argos! 🚀"
