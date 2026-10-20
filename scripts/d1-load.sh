#!/usr/bin/env bash
# Apply worker/schema.sql and every SQL chunk in a directory to the remote D1
# database, then refresh the /salud aggregates and make sure the database stays
# under the included storage (no recurring cost).
#
# D1 runs one import at a time per database, so every call is retried with
# backoff (parallel loads and the daily ETL can collide).
#
# Usage: scripts/d1-load.sh <dir>
# Env:   D1_MAX_BYTES (default 4.5 GB), CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
set -euo pipefail

DIR="$1"
DB="licit"
MAX_BYTES="${D1_MAX_BYTES:-4500000000}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRANGLER="npx --yes wrangler@4"
ATTEMPTS=12

d1() {
  local label="$1"
  shift
  for attempt in $(seq 1 "$ATTEMPTS"); do
    if $WRANGLER d1 execute "$DB" --remote --yes "$@" > /dev/null; then
      echo "Applied $label"
      return 0
    fi
    echo "Retrying $label (attempt $attempt)"
    sleep $((attempt < 6 ? attempt * 30 : 180))
  done
  echo "Failed $label"
  return 1
}

d1 schema --file "$ROOT/worker/schema.sql"

for f in "$DIR"/d1-*.sql; do
  [ -e "$f" ] || continue
  d1 "$(basename "$f")" --file "$f"
done

# Precompute landing/health aggregates once per load (read by GET /salud).
d1 stats --command "
  INSERT INTO meta (clave, valor)
  SELECT 'stats', json_object(
    'total_licitaciones', count(*),
    'total_organos', count(DISTINCT organo_id),
    'total_empresas', count(DISTINCT adjudicatario_nif),
    'importe_total', round(coalesce(sum(presupuesto_sin_iva), 0)),
    'desde', min(fecha_publicacion),
    'ultima_actualizacion', max(fecha_actualizacion))
  FROM licitacion
  WHERE true
  ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;"

SIZE=$($WRANGLER d1 info "$DB" --json | jq -r .database_size)
echo "D1 size: $((SIZE / 1000000)) MB (limit $((MAX_BYTES / 1000000)) MB)"
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  echo "::error::D1 supera ${MAX_BYTES} bytes: revisar antes de que genere coste"
  exit 1
fi
