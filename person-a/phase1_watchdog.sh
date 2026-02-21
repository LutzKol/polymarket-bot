#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

INTERVAL_SEC=60
ONCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      INTERVAL_SEC="$2"
      shift 2
      ;;
    --once)
      ONCE=1
      shift
      ;;
    *)
      echo "Unbekannte Option: $1"
      echo "Usage: bash phase1_watchdog.sh [--interval N] [--once]"
      exit 1
      ;;
  esac
done

if ! [[ "$INTERVAL_SEC" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SEC" -lt 5 ]]; then
  echo "--interval muss eine Zahl >= 5 sein"
  exit 1
fi

mkdir -p logs
WATCHDOG_LOG="logs/phase1_watchdog.log"
RESTARTS=0
LAST_ROWS=-1
NO_GROWTH_CYCLES=0
EXTERNAL_ACTIVITY_WINDOW_SEC=90

now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

csv_rows() {
  if [[ -f oracle_lag_log.csv ]]; then
    local lines
    lines="$(wc -l < oracle_lag_log.csv)"
    if [[ "$lines" -gt 0 ]]; then
      echo $((lines - 1))
    else
      echo 0
    fi
  else
    echo 0
  fi
}

monitor_running() {
  local pid_file="logs/phase1_monitor.pid"
  if [[ ! -f "$pid_file" ]]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file" || true)"
  if [[ -z "$pid" ]]; then
    return 1
  fi

  kill -0 "$pid" 2>/dev/null
}

csv_last_update_age_sec() {
  local csv_file="oracle_lag_log.csv"
  if [[ ! -f "$csv_file" ]]; then
    echo 999999
    return
  fi

  local now epoch
  now="$(date +%s)"
  # macOS/BSD stat
  if epoch="$(stat -f %m "$csv_file" 2>/dev/null)"; then
    :
  # GNU stat fallback
  elif epoch="$(stat -c %Y "$csv_file" 2>/dev/null)"; then
    :
  else
    echo 999999
    return
  fi
  echo $((now - epoch))
}

start_monitor() {
  bash "$ROOT_DIR/start_phase1_monitor.sh" >> "$WATCHDOG_LOG" 2>&1 || true
}

heartbeat() {
  local status="$1"
  local rows="$2"
  local ts
  ts="$(now_utc)"
  echo "[$ts] status=${status} rows=${rows} restarts=${RESTARTS} no_growth_cycles=${NO_GROWTH_CYCLES}" | tee -a "$WATCHDOG_LOG"
}

echo "[$(now_utc)] Watchdog gestartet (interval=${INTERVAL_SEC}s)" | tee -a "$WATCHDOG_LOG"

while true; do
  if monitor_running; then
    rows="$(csv_rows)"
    if [[ "$LAST_ROWS" -ge 0 ]] && [[ "$rows" -le "$LAST_ROWS" ]]; then
      NO_GROWTH_CYCLES=$((NO_GROWTH_CYCLES + 1))
    else
      NO_GROWTH_CYCLES=0
    fi
    LAST_ROWS="$rows"
    heartbeat "RUNNING" "$rows"
  else
    rows="$(csv_rows)"
    age_sec="$(csv_last_update_age_sec)"
    if [[ "$age_sec" -le "$EXTERNAL_ACTIVITY_WINDOW_SEC" ]]; then
      if [[ "$LAST_ROWS" -ge 0 ]] && [[ "$rows" -le "$LAST_ROWS" ]]; then
        NO_GROWTH_CYCLES=$((NO_GROWTH_CYCLES + 1))
      else
        NO_GROWTH_CYCLES=0
      fi
      LAST_ROWS="$rows"
      heartbeat "EXTERNAL_ACTIVE" "$rows"
    else
      echo "[$(now_utc)] Monitor nicht aktiv und keine frische CSV-Aktivität -> starte neu" | tee -a "$WATCHDOG_LOG"
      start_monitor
      RESTARTS=$((RESTARTS + 1))
      rows="$(csv_rows)"
      LAST_ROWS="$rows"
      NO_GROWTH_CYCLES=0
      heartbeat "RESTARTED" "$rows"
    fi
  fi

  if [[ "$ONCE" -eq 1 ]]; then
    break
  fi

  sleep "$INTERVAL_SEC"
done
