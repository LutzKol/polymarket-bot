#!/usr/bin/env python3
"""Analyze oracle lag events from oracle_lag_log.csv."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class Tick:
    timestamp: datetime
    lag_pct: float


@dataclass
class Event:
    start: datetime
    end: datetime
    max_abs_lag_pct: float
    max_signed_lag_pct: float
    ticks: int


def parse_iso_ts(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def load_ticks(csv_path: Path) -> list[Tick]:
    ticks: list[Tick] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = parse_iso_ts(row.get("timestamp_utc", ""))
            lag_raw = (row.get("lag_pct") or "").strip()
            if ts is None or not lag_raw:
                continue
            try:
                lag_pct = float(lag_raw)
            except ValueError:
                continue
            ticks.append(Tick(timestamp=ts, lag_pct=lag_pct))
    ticks.sort(key=lambda t: t.timestamp)
    return ticks


def iter_events(ticks: Iterable[Tick], threshold_pct: float) -> Iterable[Event]:
    current: list[Tick] = []

    def build_event(event_ticks: list[Tick]) -> Event:
        strongest = max(event_ticks, key=lambda t: abs(t.lag_pct))
        return Event(
            start=event_ticks[0].timestamp,
            end=event_ticks[-1].timestamp,
            max_abs_lag_pct=abs(strongest.lag_pct),
            max_signed_lag_pct=strongest.lag_pct,
            ticks=len(event_ticks),
        )

    for tick in ticks:
        if abs(tick.lag_pct) > threshold_pct:
            current.append(tick)
            continue
        if current:
            yield build_event(current)
            current = []

    if current:
        yield build_event(current)


def format_duration_seconds(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds())


def _load_config_threshold(config_path: str = "config.json") -> float:
    """Read alert_threshold_pct from config.json, fallback to 0.3."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return float(cfg.get("alert_threshold_pct", 0.3))
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        return 0.3


def main() -> int:
    config_default = _load_config_threshold()

    parser = argparse.ArgumentParser(description="Analyze lag events from oracle_lag_log.csv")
    parser.add_argument("--csv", default="oracle_lag_log.csv", help="Path to lag CSV file")
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=f"Absolute lag threshold in percent (default: {config_default} from config.json)",
    )
    parser.add_argument("--min-events", type=int, default=2, help="Target minimum number of events")
    args = parser.parse_args()

    if args.threshold is None:
        args.threshold = config_default

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}")
        return 1

    ticks = load_ticks(csv_path)
    if not ticks:
        print("No valid ticks found in CSV yet.")
        return 0

    events = list(iter_events(ticks, threshold_pct=args.threshold))

    first_ts = ticks[0].timestamp
    last_ts = ticks[-1].timestamp
    sample_hours = (last_ts - first_ts).total_seconds() / 3600.0

    print("Lag Analysis Summary")
    print(f"- Ticks analyzed: {len(ticks)}")
    print(f"- Sample window: {first_ts.isoformat()} to {last_ts.isoformat()} ({sample_hours:.2f}h)")
    print(f"- Threshold: |lag_pct| > {args.threshold:.3f}%")
    print(f"- Events found: {len(events)}")

    if events:
        print("\nEvents:")
        for i, ev in enumerate(events, start=1):
            direction = "UP" if ev.max_signed_lag_pct > 0 else "DOWN"
            dur_s = format_duration_seconds(ev.start, ev.end)
            print(
                f"{i}. {ev.start.isoformat()} -> {ev.end.isoformat()}  "
                f"dur={dur_s}s  max={ev.max_signed_lag_pct:+.4f}% ({direction})  ticks={ev.ticks}"
            )

    met = len(events) >= args.min_events
    print("\nPhase-1 Event Criterion:")
    print(f"- Required events: >= {args.min_events}")
    print(f"- Status: {'PASS' if met else 'NOT YET'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
