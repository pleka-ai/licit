#!/usr/bin/env bash
# Apply every SQL chunk in a directory to the remote D1 database, then make
# sure the database stays under the included storage (no recurring cost).
#
# Usage: scripts/d1-load.sh <dir>
# Env:   D1_MAX_BYTES (default 4.5 GB), CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
set -euo pipefail

DIR="$1"
DB="licit"
MAX_BYTES="${D1_MAX_BYTES:-4500000000}"
WRANGLER="npx --yes wrangler@4"

for f in "$DIR"/d1-*.sql; do
  [ -e "$f" ] || continue
  for attempt in 1 2 3 4 5; do
    if $WRANGLER d1 execute "$DB" --remote --yes --file "$f" > /dev/null; then
      echo "Applied $(basename "$f")"
      break
    fi
    [ "$attempt" = 5 ] && { echo "Failed to apply $f"; exit 1; }
    echo "Retrying $(basename "$f") (attempt $attempt)"
    sleep $((attempt * 30))
  done
done

SIZE=$($WRANGLER d1 info "$DB" --json | jq -r .database_size)
echo "D1 size: $((SIZE / 1000000)) MB (limit $((MAX_BYTES / 1000000)) MB)"
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  echo "::error::D1 supera ${MAX_BYTES} bytes: revisar antes de que genere coste"
  exit 1
fi

# Precompute landing/health aggregates once per load (read by GET /salud).
$WRANGLER d1 execute "$DB" --remote --yes --command "
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
  ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;" > /dev/null
echo "Stats refreshed"
