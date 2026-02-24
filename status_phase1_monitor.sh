#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PID_FILE="logs/phase1_monitor.pid"
CSV_FILE="oracle_lag_log.csv"
EXTERNAL_ACTIVITY_WINDOW_SEC=90

csv_last_update_age_sec() {
  if [[ ! -f "$CSV_FILE" ]]; then
    echo 999999
    return
  fi

  local now epoch
  now="$(date +%s)"
  # macOS/BSD stat
  if epoch="$(stat -f %m "$CSV_FILE" 2>/dev/null)"; then
    :
  # GNU stat fallback
  elif epoch="$(stat -c %Y "$CSV_FILE" 2>/dev/null)"; then
    :
  else
    echo 999999
    return
  fi
  echo $((now - epoch))
}

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "Monitor status: RUNNING (PID $PID)"
  else
    age_sec="$(csv_last_update_age_sec)"
    if [[ "$age_sec" -le "$EXTERNAL_ACTIVITY_WINDOW_SEC" ]]; then
      echo "Monitor status: RUNNING (external/unmanaged, stale PID file)"
    else
      echo "Monitor status: NOT RUNNING (stale PID file)"
    fi
  fi
else
  age_sec="$(csv_last_update_age_sec)"
  if [[ "$age_sec" -le "$EXTERNAL_ACTIVITY_WINDOW_SEC" ]]; then
    echo "Monitor status: RUNNING (external/unmanaged)"
  else
    echo "Monitor status: NOT RUNNING"
  fi
fi

if [[ -f "$CSV_FILE" ]]; then
  LINES="$(wc -l < "$CSV_FILE")"
  DATA_ROWS=$(( LINES > 0 ? LINES - 1 : 0 ))
  echo "CSV rows: $DATA_ROWS"
  echo "CSV file: $CSV_FILE"
else
  echo "CSV file not found: $CSV_FILE"
fi

LATEST_LOG="$(ls -1t logs/phase1_monitor_*.log 2>/dev/null | head -n 1 || true)"
if [[ -n "$LATEST_LOG" ]]; then
  echo "Latest log: $LATEST_LOG"
  echo "--- tail ---"
  tail -n 10 "$LATEST_LOG"
fi
