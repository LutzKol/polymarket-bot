#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

mkdir -p logs
PID_FILE="logs/phase1_monitor.pid"
TS="$(date -u +"%Y%m%dT%H%M%SZ")"
LOG_FILE="logs/phase1_monitor_${TS}.log"

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${EXISTING_PID}" ]] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "Phase 1 monitor already running (PID $EXISTING_PID)."
    echo "Use ./status_phase1_monitor.sh or ./stop_phase1_monitor.sh first."
    exit 1
  fi
fi

nohup python3 -u oracle_monitor.py >> "$LOG_FILE" 2>&1 &
NEW_PID="$!"
echo "$NEW_PID" > "$PID_FILE"

echo "Started Phase 1 monitor"
echo "- PID: $NEW_PID"
echo "- Log: $LOG_FILE"
echo "- CSV: oracle_lag_log.csv"
