#!/usr/bin/env bash
# End-to-end rehearsal of the ETL and Historico pipeline on the test fixtures,
# with the same commands the workflows run: parser CLI → Postgres → raw →
# model → D1 (wrangler's local database) on two days, then the API on
# `wrangler dev`. Run by the test workflow; locally needs DATABASE_URL pointing
# at a rehearsal Postgres with schema/ applied (its ingested rows are emptied).
#
# The BORME fixtures (tests/borme/fixtures) go through borme.raw and into the
# model; one of their companies is a winner in the PLACSP fixtures.
#
# Usage: scripts/ensayo-pipeline.sh <work_dir>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mkdir -p "$1" && cd "$1" && pwd)"
FIX="$ROOT/tests/etl/fixtures"
PG_URL="${DATABASE_URL:?DATABASE_URL apunta al Postgres de ensayo}"
export PYTHONPATH="$ROOT/src" ENVIRONMENT="${ENVIRONMENT:-ci}"
export D1_DATABASE="${D1_DATABASE:-licit-datos}" D1_TARGET=local D1_PERSIST_TO="$WORK/d1-local"
WRANGLER="npx --yes wrangler@4"
py() { uv run --project "$ROOT" python "$@"; }
# Publishing never sees Postgres, as in the workflows.
publish() { env -u DATABASE_URL "$@"; }
d1_count() {
  $WRANGLER d1 execute "$D1_DATABASE" --local --persist-to "$D1_PERSIST_TO" --json \
    --command "$1" | jq -r '.[0].results[0].n'
}
expect() {
  [ "$2" = "$3" ] || { echo "FALLO: $1: esperado $3, obtenido $2"; exit 1; }
  echo "ok: $1 = $3"
}
feed() {  # feed <dir> <feed_type> <year> <fixture>
  local root
  case "$2" in
    outsiders) root=PlataformasAgregadasSinMenores.atom ;;
    insiders) root=licitacionesPerfilesContratanteCompleto3.atom ;;
  esac
  mkdir -p "$1/$2/$3"
  cp "$FIX/$4" "$1/$2/$3/$root"
}

rm -rf "$WORK"/{feeds-1,feeds-2,raw,modelo-1,modelo-2,d1-1,d1-2,d1-local,borme-cache,borme-raw}
py - <<'PY'
import asyncio, os
import asyncpg

async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    await conn.execute(
        "TRUNCATE contract_folder_status, contracting_party, etl_sync_state,"
        " etl_failed_entries CASCADE"
    )
    await conn.close()

asyncio.run(main())
PY

echo "== BORME: fixtures por el parser y el export raw"
for xml in "$ROOT"/tests/borme/fixtures/BORME-A-*.xml; do
  year=$(basename "$xml" | cut -d- -f3)
  mkdir -p "$WORK/borme-cache/$year"
  cp "$xml" "$WORK/borme-cache/$year/"
done
py -m borme.raw "$WORK/borme-cache" "$WORK/borme-raw"
export BORME_RAW="$WORK/borme-raw"

echo "== Día 1: dos expedientes por el CLI del parser"
feed "$WORK/feeds-1" outsiders 2024 full_entry.xml
feed "$WORK/feeds-1" insiders 2024 multi_lot_with_terms.xml
py -m etl.handlers.feed_reader --local "$WORK/feeds-1" --years 2024
py -m export.raw "$WORK/raw/dia-1"
publish "$ROOT/scripts/modelo.sh" "$WORK/raw/todo-1" "$WORK/modelo-1" "$WORK/raw/dia-1"
publish "$ROOT/scripts/d1-sql.sh" "$WORK/d1-1" "$WORK/modelo-1" "$WORK/sin-modelo-previo"
(cd "$ROOT" && "$ROOT/scripts/d1-load.sh" "$WORK/d1-1")
expect "licitaciones en D1 tras la carga completa" "$(d1_count 'SELECT count(*) n FROM licitacion_api')" 2
expect "adjudicatarias con registro" "$(d1_count 'SELECT count(*) n FROM empresa_registro')" 1

echo "== Día 2: un expediente nuevo, carga por diferencias"
feed "$WORK/feeds-2" outsiders 2025 minimal_entry.xml
py -m etl.handlers.feed_reader --local "$WORK/feeds-2" --years 2025
py -m export.raw "$WORK/raw/dia-2"
publish "$ROOT/scripts/modelo.sh" "$WORK/raw/todo-2" "$WORK/modelo-2" "$WORK/raw/todo-1" "$WORK/raw/dia-2"
publish "$ROOT/scripts/d1-sql.sh" "$WORK/d1-2" "$WORK/modelo-2" "$WORK/d1-1/baseline"
(cd "$ROOT" && "$ROOT/scripts/d1-load.sh" "$WORK/d1-2")
expect "licitaciones en D1 tras el diff" "$(d1_count 'SELECT count(*) n FROM licitacion_api')" 3
expect "historial de estados" "$(d1_count 'SELECT count(*) n FROM cambio_estado')" 3

echo "== API sobre el D1 local"
PORT="${ENSAYO_PORT:-8799}"
if curl -s -o /dev/null "http://localhost:$PORT"; then
  echo "FALLO: el puerto $PORT ya está en uso (ENSAYO_PORT para usar otro)"; exit 1
fi
(cd "$ROOT" && exec $WRANGLER dev --local --port "$PORT" --persist-to "$D1_PERSIST_TO" \
  > "$WORK/wrangler-dev.log" 2>&1) &
DEV=$!
# npx starts wrangler, which starts workerd: stop the whole tree.
descendants() {
  local child
  for child in $(pgrep -P "$1" 2> /dev/null); do
    descendants "$child"
    echo "$child"
  done
}
# shellcheck disable=SC2046
stop_dev() { kill $(descendants "$DEV") "$DEV" 2> /dev/null || true; }
trap stop_dev EXIT
for _ in $(seq 1 60); do
  curl -sf "http://localhost:$PORT/api/salud" > /dev/null && break
  sleep 2
done
total=$(curl -sf -X POST "http://localhost:$PORT/api/v1/buscar" \
  -H 'content-type: application/json' -d '{"limit": 5}' | jq -r .total)
expect "total de /v1/buscar" "$total" 3
id=$(curl -sf -X POST "http://localhost:$PORT/api/v1/buscar" \
  -H 'content-type: application/json' -d '{"limit": 1}' | jq -r '.resultados[0].id')
campos=$(curl -sf "http://localhost:$PORT/api/v1/licitacion/$id" | jq 'keys | length')
expect "campos de la ficha" "$campos" 42
api() { curl -sf "http://localhost:$PORT/api/$1"; }
buscar() { curl -sf -X POST "http://localhost:$PORT/api/v1/buscar" -H 'content-type: application/json' -d "$1"; }
expect "orden por importe" "$(buscar '{"ordenar": "importe", "limit": 5}' | jq '.resultados | length')" 3
organo=$(buscar '{"limit": 5}' | jq -r '[.resultados[] | select(.organo_id)][0].organo_id')
expect "licitaciones del órgano" "$(api "v1/organo/$organo" | jq '.stats.contratos > 0')" true
nif=$(buscar '{"limit": 5}' | jq -r '[.resultados[] | select(.adjudicatario_nif)][0].adjudicatario_nif')
expect "contratos de la empresa" "$(api "v1/empresa/$nif" | jq '.stats.contratos > 0')" true
expect "similares responde" "$(api "v1/similares/$id" | jq 'has("resultados")')" true
registro=$(api "v1/empresa/B12345678")
expect "registro de la empresa" "$(echo "$registro" | jq -r '.registro.sociedad')" "TECHCORP SOCIEDAD LIMITADA"
expect "cargos vigentes" "$(echo "$registro" | jq -r '.registro.cargos_vigentes[0].nombre')" "SOLER VIDAL MARC"
echo "Ensayo completo"
