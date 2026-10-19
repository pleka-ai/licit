#!/bin/bash
set -euo pipefail

# Zero-downtime deploy for licit.
# Called by GitHub Actions after tests pass on main.

COMPOSE_FILE="$(cd "$(dirname "$0")" && pwd)/docker-compose.yml"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE="docker compose --env-file $PROJECT_DIR/.env -f $COMPOSE_FILE"

cd "$PROJECT_DIR"

echo "==> Building images"
$COMPOSE build api etl-cron schema-init

echo "==> Applying schema migrations"
$COMPOSE run --rm schema-init

echo "==> Zero-downtime API deploy"
OLD_ID=$($COMPOSE ps -q api 2>/dev/null || true)

if [ -n "$OLD_ID" ]; then
  # Blue-green: start new container alongside old one
  $COMPOSE up -d --no-deps --scale api=2 --no-recreate api

  echo "Waiting for new API instance to be healthy..."
  for i in $(seq 1 30); do
    NEW_ID=$($COMPOSE ps -q api | grep -v "$OLD_ID" | head -1)
    if [ -n "$NEW_ID" ]; then
      STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$NEW_ID" 2>/dev/null || echo "starting")
      if [ "$STATUS" = "healthy" ]; then
        echo "New instance healthy, removing old..."
        docker stop "$OLD_ID" && docker rm "$OLD_ID"
        $COMPOSE up -d --no-deps --scale api=1 --no-recreate api
        break
      fi
    fi
    if [ "$i" -eq 30 ]; then
      echo "ERROR: new instance not healthy after 60s, rolling back"
      [ -n "${NEW_ID:-}" ] && docker stop "$NEW_ID" && docker rm "$NEW_ID"
      $COMPOSE up -d --no-deps --scale api=1 --no-recreate api
      exit 1
    fi
    sleep 2
  done
else
  # First deploy or API not running
  $COMPOSE up -d --no-deps api
fi

echo "==> Updating ETL cron"
$COMPOSE up -d --no-deps etl-cron

echo "==> Cleanup"
docker image prune -f

echo "==> Deploy complete"
