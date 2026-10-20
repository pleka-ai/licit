#!/usr/bin/env bash
# Apply worker/schema.sql and every SQL chunk in a directory (in name order:
# licitacion d1-0001… then derived tables d1-9001…, see export.derived) to the
# remote D1 database, and make sure it stays under the included storage.
#
# D1 runs one import at a time per database: local callers are serialised
# with a lock, and every call is retried with backoff in case another runner
# (the daily ETL) is importing.
#
# Usage: scripts/d1-load.sh <dir>
# Env:   D1_DATABASE (default licit-api), D1_MAX_BYTES (default 4.5 GB),
#        CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
set -euo pipefail

DIR="$1"
DB="${D1_DATABASE:-licit-api}"
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

LOCK="${TMPDIR:-/tmp}/licit-d1-${DB}.lock"
until mkdir "$LOCK" 2> /dev/null; do sleep 5; done
trap 'rmdir "$LOCK"' EXIT

d1 schema --file "$ROOT/worker/schema.sql"

for f in "$DIR"/d1-*.sql; do
  [ -e "$f" ] || continue
  d1 "$(basename "$f")" --file "$f"
done

SIZE=$($WRANGLER d1 info "$DB" --json | jq -r .database_size)
echo "D1 size: $((SIZE / 1000000)) MB (limit $((MAX_BYTES / 1000000)) MB)"
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  echo "::error::D1 supera ${MAX_BYTES} bytes: revisar antes de que genere coste"
  exit 1
fi
