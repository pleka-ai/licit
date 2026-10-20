#!/usr/bin/env bash
# Initial load from a workstation instead of GitHub Actions (no 6 h limit,
# several years in parallel). Afterwards the daily etl.yml takes over.
#
#   scripts/backfill-local.sh historico 2017 2018 ...   # frozen years → raw Parquet
#   scripts/backfill-local.sh estado 2025 2026          # rolling window → raw Parquet + state dump
#   scripts/backfill-local.sh modelo                    # raw history → model → R2 + D1
#
# Requires docker, uv, jq and env: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID,
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (R2 S3 keys).
# Optional: PARALLEL (default 4), PG_PORT (default 55500).
set -euo pipefail

MODE="${1:?modo: historico | estado | modelo}"
shift
YEARS=("$@")
[ "${#YEARS[@]}" -gt 0 ] || [ "$MODE" = modelo ] || { echo "faltan años"; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/out/backfill"
PARALLEL="${PARALLEL:-4}"
PG_PORT="${PG_PORT:-55500}"
PG="licit-backfill"
export AWS_DEFAULT_REGION=auto
export AWS_ENDPOINT_URL="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
export ENVIRONMENT=backfill PYTHONPATH="$ROOT/src"
BUCKET="s3://licit-data"
aws() { uvx --from awscli aws "$@"; }

mkdir -p "$OUT/logs"
cd "$ROOT"

if ! docker ps --format '{{.Names}}' | grep -qx "$PG"; then
  docker run -d --name "$PG" -p "127.0.0.1:${PG_PORT}:5432" --shm-size=1g \
    -e POSTGRES_USER=licit -e POSTGRES_PASSWORD=licit -e POSTGRES_DB=licit \
    postgres:16-alpine -c max_connections=300 -c shared_buffers=1GB > /dev/null
  until docker exec "$PG" pg_isready -U licit > /dev/null 2>&1; do sleep 1; done
  docker exec "$PG" apk add -q bash > /dev/null
fi
docker cp "$ROOT/schema/." "$PG:/schema"

fresh_db() {
  docker exec "$PG" dropdb -U licit --if-exists "$1"
  docker exec "$PG" createdb -U licit "$1"
  docker exec -e DATABASE_URL="postgresql://licit:licit@localhost:5432/$1" "$PG" \
    bash /schema/apply.sh > /dev/null
}

historico_year() {
  set -euo pipefail
  local year="$1" db="licit_$1"
  export DATABASE_URL="postgresql://licit:licit@localhost:${PG_PORT}/$db"
  echo "[$year] start $(date +%T)"
  fresh_db "$db"
  uv run python -m etl.handlers.feed_reader --seed --years "$year"
  rm -rf "$OUT/raw/historico/$year"
  uv run python -m export.raw "$OUT/raw/historico/$year"
  aws s3 cp "$OUT/raw/historico/$year" "$BUCKET/parquet/raw/historico/$year/" --recursive --only-show-errors
  docker exec "$PG" dropdb -U licit "$db"
  echo "[$year] done $(date +%T)"
}

estado() {
  export DATABASE_URL="postgresql://licit:licit@localhost:${PG_PORT}/licit_estado"
  echo "[estado] start $(date +%T)"
  fresh_db licit_estado
  uv run python -m etl.handlers.feed_reader --seed --years "$@"
  uv run python -m etl.handlers.feed_reader
  uv run python -m export.prune
  rm -rf "$OUT/raw/reciente"
  uv run python -m export.raw "$OUT/raw/reciente"
  aws s3 cp "$OUT/raw/reciente" "$BUCKET/parquet/raw/reciente/" --recursive --only-show-errors
  docker exec "$PG" pg_dump -U licit -Fc -Z 9 --no-owner -d licit_estado -f /tmp/state.dump
  docker cp "$PG:/tmp/state.dump" "$OUT/state.dump"
  aws s3 cp "$OUT/state.dump" "$BUCKET/state/licit.dump" --only-show-errors
  echo "[estado] done $(date +%T) dump=$(du -h "$OUT/state.dump" | cut -f1)"
}

# Same steps as historico.yml's consolidar job: every archived year (oldest
# first), then the window, merged into the raw history; model; D1 by diff
# against the tables D1 last received (full load when there is none).
modelo() {
  echo "[modelo] start $(date +%T)"
  rm -rf "$OUT/raw" "$OUT/modelo" "$OUT/modelo-d1" "$OUT/d1"
  aws s3 cp "$BUCKET/parquet/raw/historico/" "$OUT/raw/historico" --recursive --only-show-errors
  aws s3 cp "$BUCKET/parquet/raw/reciente/" "$OUT/raw/reciente" --recursive --only-show-errors
  local srcs
  srcs="$(find "$OUT/raw/historico" -mindepth 1 -maxdepth 1 -type d | sort) $OUT/raw/reciente"
  # shellcheck disable=SC2086
  uv run python -m export.compact "$OUT/raw/todo" $srcs
  aws s3 cp "$OUT/raw/todo" "$BUCKET/parquet/raw/todo/" --recursive --only-show-errors
  uv run python -m export.modelo "$OUT/modelo" "$OUT/raw/todo"
  aws s3 cp "$OUT/modelo" "$BUCKET/parquet/modelo/" --recursive --only-show-errors
  aws s3 cp "$BUCKET/state/modelo-d1/" "$OUT/modelo-d1" --recursive --only-show-errors
  uv run python -m export.d1 "$OUT/d1" "$OUT/modelo" "$OUT/modelo-d1"
  uv run python -m export.derived "$OUT/d1" "$OUT/modelo"
  "$ROOT/scripts/d1-load.sh" "$OUT/d1"
  aws s3 sync "$OUT/d1/baseline" "$BUCKET/state/modelo-d1/" --delete --only-show-errors
  echo "[modelo] done $(date +%T)"
}

export -f historico_year fresh_db aws
export ROOT OUT PG PG_PORT BUCKET

case "$MODE" in
  historico)
    printf '%s\n' "${YEARS[@]}" | xargs -P "$PARALLEL" -I{} \
      bash -c '( historico_year {} ) > "$OUT/logs/{}.log" 2>&1; rc=$?
        if [ "$rc" = 0 ]; then echo "OK {}"; else echo "FALLO {} (ver $OUT/logs/{}.log)"; exit 1; fi'
    ;;
  estado)
    estado "${YEARS[@]}" 2>&1 | tee "$OUT/logs/estado.log"
    ;;
  modelo)
    modelo 2>&1 | tee "$OUT/logs/modelo.log"
    ;;
  *) echo "modo desconocido: $MODE"; exit 1 ;;
esac
