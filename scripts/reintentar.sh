#!/usr/bin/env bash
# Run a command up to REINTENTOS times (default 3), waiting longer each time.
# For idempotent R2 transfers (aws s3 cp/sync): R2 sometimes rejects a
# multipart upload (InvalidPart) and the AWS CLI does not retry that.
#
# Usage: scripts/reintentar.sh aws s3 sync <src> <dst> ...
set -uo pipefail

attempts="${REINTENTOS:-3}"
for i in $(seq 1 "$attempts"); do
  "$@" && exit 0
  status=$?
  [ "$i" -lt "$attempts" ] || break
  echo "reintentar: intento $i/$attempts falló ($status): ${*:1:3}" >&2
  sleep $((i * 15))
done
exit "$status"
