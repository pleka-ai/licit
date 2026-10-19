#!/usr/bin/env bash
# Initial load from a workstation instead of GitHub Actions (no 6 h limit,
# several years in parallel). Afterwards the daily etl.yml takes over.
#
#   scripts/backfill-local.sh historico 2017 2018 ...   # frozen years → D1 + Parquet
#   scripts/backfill-local.sh estado 2025 2026          # rolling window → D1 + Parquet + state dump
#
# Requires docker, uv, jq and env: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID,
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY (R2 S3 keys).
# Optional: PARALLEL (default 4), PG_PORT (default 55500).
set -euo pipefail

MODE="${1:?modo: historico | estado}"
shift
YEARS=("$@")
[ "${#YEARS[@]}" -gt 0 ] || { echo "faltan años"; exit 1; }

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

load_d1() {
  npx --yes wrangler@4 d1 execute licit --remote --yes --file worker/schema.sql > /dev/null
  "$ROOT/scripts/d1-load.sh" "$1"
}

historico_year() {
  local year="$1" db="licit_$1"
  export DATABASE_URL="postgresql://licit:licit@localhost:${PG_PORT}/$db"
  echo "[$year] start $(date +%T)"
  fresh_db "$db"
  uv run python -m etl.handlers.feed_reader --seed --years "$year"
  uv run python -m export.parquet "$OUT/historico/$year"
  aws s3 cp "$OUT/historico/$year" "$BUCKET/parquet/historico/$year/" --recursive --only-show-errors
  uv run python -m export.d1 build "$OUT/d1-$year" --todo
  load_d1 "$OUT/d1-$year"
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
  uv run python -m export.parquet "$OUT/reciente"
  aws s3 cp "$OUT/reciente" "$BUCKET/parquet/reciente/" --recursive --only-show-errors
  rm -rf "$OUT/d1-estado"
  uv run python -m export.d1 build "$OUT/d1-estado"
  load_d1 "$OUT/d1-estado"
  uv run python -m export.d1 commit "$OUT/d1-estado/pending.json"
  docker exec "$PG" pg_dump -U licit -Fc -Z 9 --no-owner \
    --exclude-table-data=api_user --exclude-table-data=api_key \
    --exclude-table-data=audit_log -d licit_estado -f /tmp/state.dump
  docker cp "$PG:/tmp/state.dump" "$OUT/state.dump"
  aws s3 cp "$OUT/state.dump" "$BUCKET/state/licit.dump" --only-show-errors
  echo "[estado] done $(date +%T) dump=$(du -h "$OUT/state.dump" | cut -f1)"
}

export -f historico_year fresh_db load_d1 aws
export ROOT OUT PG PG_PORT BUCKET

case "$MODE" in
  historico)
    printf '%s\n' "${YEARS[@]}" | xargs -P "$PARALLEL" -I{} \
      bash -c 'historico_year {} > "$OUT/logs/{}.log" 2>&1 && echo "OK {}" || echo "FALLO {} (ver $OUT/logs/{}.log)"'
    ;;
  estado)
    estado "${YEARS[@]}" 2>&1 | tee "$OUT/logs/estado.log"
    ;;
  *) echo "modo desconocido: $MODE"; exit 1 ;;
esac
