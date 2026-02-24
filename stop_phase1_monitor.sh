#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PID_FILE="logs/phase1_monitor.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found. Monitor is likely not running."
  exit 0
fi

PID="$(cat "$PID_FILE" || true)"
if [[ -z "$PID" ]]; then
  echo "PID file is empty. Removing stale PID file."
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Sent SIGTERM to monitor PID $PID"
else
  echo "Monitor PID $PID is not running."
fi

rm -f "$PID_FILE"
echo "Stopped Phase 1 monitor and removed PID file."
