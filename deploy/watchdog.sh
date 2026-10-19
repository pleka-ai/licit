#!/bin/bash
# Monitor container health and system resources.
# Intended to run every 5 minutes via the host crontab.
#
# Set DISCORD_WEBHOOK_URL in .env (project root) to receive alerts.
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$COMPOSE_DIR/.." && pwd)"
COMPOSE="docker compose --env-file $PROJECT_DIR/.env -f $COMPOSE_DIR/docker-compose.yml"
LOG="/var/log/licit-watchdog.log"
STATE_DIR="/tmp/licit-watchdog"
mkdir -p "$STATE_DIR"

# Load .env from project root for DISCORD_WEBHOOK_URL
if [ -f "$PROJECT_DIR/.env" ]; then
  # shellcheck source=/dev/null
  set -a; source "$PROJECT_DIR/.env"; set +a
fi

notify() {
  local msg="$1"
  echo "$(date -Iseconds) $msg" >> "$LOG"
  if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
    curl -sf -H "Content-Type: application/json" \
      -d "{\"content\":\"$msg\"}" \
      "$DISCORD_WEBHOOK_URL" > /dev/null 2>&1 || true
  fi
}

# Throttle: only alert once per key per hour
should_alert() {
  local key="$1"
  local file="$STATE_DIR/$key"
  if [ -f "$file" ]; then
    local last
    last=$(cat "$file")
    local now
    now=$(date +%s)
    if (( now - last < 3600 )); then
      return 1
    fi
  fi
  date +%s > "$file"
  return 0
}

# ── Container health ──────────────────────────────────────────────
for svc in api postgres; do
  health=$($COMPOSE ps --format '{{.Health}}' "$svc" 2>/dev/null || echo "unknown")
  if [ "$health" = "unhealthy" ]; then
    $COMPOSE restart "$svc"
    notify "⚠️ **$svc** unhealthy — restarted on $(hostname)"
  fi
done

# ── Disk usage ────────────────────────────────────────────────────
disk_pct=$(df / --output=pcent | tail -1 | tr -d ' %')
if [ "$disk_pct" -gt 90 ] && should_alert "disk"; then
  notify "🟠 Disk at **${disk_pct}%** on $(hostname)"
fi

# ── Memory usage ──────────────────────────────────────────────────
mem_pct=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
if [ "$mem_pct" -gt 90 ] && should_alert "memory"; then
  notify "🟠 Memory at **${mem_pct}%** on $(hostname)"
fi

# ── Load average ──────────────────────────────────────────────────
ncpu=$(nproc)
load_1m=$(awk '{print $1}' /proc/loadavg)
overloaded=$(awk "BEGIN {print ($load_1m > $ncpu * 2) ? 1 : 0}")
if [ "$overloaded" -eq 1 ] && should_alert "load"; then
  notify "🔴 Load average **$load_1m** (${ncpu} CPUs) on $(hostname)"
fi
