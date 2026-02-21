#!/usr/bin/env python3
"""Compact progress report for Phase 1 CSV collection."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Row:
    ts: datetime
    lag_pct: float
    alert: str


def parse_ts(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None


def load_rows(path: Path) -> list[Row]:
    out: list[Row] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            ts = parse_ts(r.get("timestamp_utc", ""))
            lag_raw = (r.get("lag_pct") or "").strip()
            if ts is None or not lag_raw:
                continue
            try:
                lag = float(lag_raw)
            except ValueError:
                continue
            out.append(Row(ts=ts, lag_pct=lag, alert=(r.get("alert") or "").strip()))
    out.sort(key=lambda x: x.ts)
    return out


def count_events(rows: list[Row], threshold: float) -> int:
    count = 0
    in_event = False
    for row in rows:
        if abs(row.lag_pct) > threshold:
            if not in_event:
                count += 1
                in_event = True
        else:
            in_event = False
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1 progress report")
    parser.add_argument("--csv", default="oracle_lag_log.csv", help="Path to oracle lag CSV")
    parser.add_argument("--event-threshold", type=float, default=0.3, help="Event threshold in percent")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV nicht gefunden: {csv_path}")
        return 1

    rows = load_rows(csv_path)
    print("Phase 1 Progress Report")
    print(f"- CSV: {csv_path}")
    print(f"- Gelesene Datenzeilen: {len(rows)}")

    if not rows:
        print("- Status: Noch keine validen Tick-Daten")
        return 0

    first = rows[0].ts
    last = rows[-1].ts
    hours = (last - first).total_seconds() / 3600.0
    max_abs_lag = max(abs(r.lag_pct) for r in rows)
    max_pos_lag = max(r.lag_pct for r in rows)
    max_neg_lag = min(r.lag_pct for r in rows)
    alerts = sum(1 for r in rows if r.alert.upper() == "ALERT")
    events = count_events(rows, threshold=args.event_threshold)

    rows_per_hour = (len(rows) / hours) if hours > 0 else 0.0

    print(f"- Zeitraum: {first.isoformat()} bis {last.isoformat()} ({hours:.2f}h)")
    print(f"- Zeilen pro Stunde: {rows_per_hour:.1f}")
    print(f"- Max |lag_pct|: {max_abs_lag:.4f}%")
    print(f"- Max positiver Lag: {max_pos_lag:.4f}%")
    print(f"- Max negativer Lag: {max_neg_lag:.4f}%")
    print(f"- ALERT-Zeilen: {alerts}")
    print(f"- Events |lag_pct| > {args.event_threshold:.3f}%: {events}")

    print("\nPhase-1 Fortschritt")
    print(f"- 48h Datenfenster: {'PASS' if hours >= 48 else 'IN PROGRESS'}")
    print(f"- >=2 Events > {args.event_threshold:.3f}%: {'PASS' if events >= 2 else 'IN PROGRESS'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
