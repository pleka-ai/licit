#!/usr/bin/env bash
# Write the SQL that brings D1 from <prev_modelo> to <modelo>: table changes
# (export.d1) and derived rows (export.derived). Without <prev_modelo>, or if
# it holds no model, a full load for an empty database. Runs without Postgres.
#
# Usage: scripts/d1-sql.sh <out_dir> <modelo> [<prev_modelo>]
set -euo pipefail

[ "$#" -ge 2 ] || { echo "uso: scripts/d1-sql.sh <out_dir> <modelo> [<prev_modelo>]"; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export PYTHONPATH="$ROOT/src"
uv run --project "$ROOT" python -m export.d1 "$@"
uv run --project "$ROOT" python -m export.derived "$1" "$2"
