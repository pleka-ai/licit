#!/usr/bin/env bash
# Version of the code that turns PLACSP archives into raw Parquet: a hash of
# the parser, the models, the Postgres schema and the raw export (not the CLI
# in src/etl/handlers, which does not change the output). Raw years
# stamped with the same version do not need to be ingested again.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
git -C "$ROOT" ls-files -s -- \
  src/etl ':!src/etl/handlers' src/shared/codice src/shared/models \
  src/shared/enums.py \
  src/export/raw.py schema ':!schema/seed.sql' \
  | git -C "$ROOT" hash-object --stdin | cut -c1-12
