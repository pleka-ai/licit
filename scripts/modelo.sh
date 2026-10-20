#!/usr/bin/env bash
# Merge raw exports into the raw history, then build the data model on it.
# Runs without Postgres. Sources go oldest first: later ones win ties.
# BORME_RAW, if set, is the BORME raw layer (one directory per year).
#
# Usage: scripts/modelo.sh <raw_todo_out> <modelo_out> <raw_src> [<raw_src>...]
set -euo pipefail

[ "$#" -ge 3 ] || { echo "uso: scripts/modelo.sh <raw_todo_out> <modelo_out> <raw_src>..."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW_OUT="$1"
MODELO_OUT="$2"
shift 2

export PYTHONPATH="$ROOT/src"
uv run --project "$ROOT" python -m export.compact "$RAW_OUT" "$@"
uv run --project "$ROOT" python -m export.modelo "$MODELO_OUT" "$RAW_OUT" ${BORME_RAW:+"$BORME_RAW"}
