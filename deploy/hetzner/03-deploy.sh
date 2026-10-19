#!/bin/bash
set -e

# Deploy or update licit on the server.
# Run as deploy user (not root).

REPO_DIR="$HOME/licit"
DEPLOY_DIR="$REPO_DIR/deploy"

if [ ! -d "$REPO_DIR" ]; then
  echo "Clonando repositorio..."
  git clone https://github.com/pleka-ai/licit.git "$REPO_DIR"
else
  echo "Actualizando repositorio..."
  cd "$REPO_DIR" && git pull --ff-only
fi

cd "$DEPLOY_DIR"

# Ensure .env exists
if [ ! -f .env ]; then
  echo "Crea deploy/.env con POSTGRES_PASSWORD y DOMAIN antes de continuar."
  exit 1
fi

echo "Construyendo y desplegando..."
docker compose up -d --build

echo "Despliegue completado."
docker compose ps
