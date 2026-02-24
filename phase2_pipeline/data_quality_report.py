#!/usr/bin/env python3
"""Data quality checks for phase3 feature CSV exports."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional


def _parse_ts(raw: str) -> Optional[datetime]:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _pct(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (part / total) * 100.0


def _quantile(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * q
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def build_report(csv_path: Path, expected_interval_s: float, gap_factor: float) -> dict:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = list(reader.fieldnames or [])

    total_rows = len(rows)
    if total_rows == 0:
        return {
            "path": str(csv_path),
            "rows": 0,
            "message": "CSV has no data rows.",
        }

    missing_counts = Counter()
    for row in rows:
        for col in columns:
            if not (row.get(col) or "").strip():
                missing_counts[col] += 1

    timestamps: list[datetime] = []
    invalid_ts_rows = 0
    for row in rows:
        ts = _parse_ts(row.get("timestamp_utc", ""))
        if ts is None:
            invalid_ts_rows += 1
            continue
        timestamps.append(ts)

    timestamps.sort()
    intervals_s: list[float] = []
    duplicate_ts = 0
    for i in range(1, len(timestamps)):
        dt = (timestamps[i] - timestamps[i - 1]).total_seconds()
        intervals_s.append(dt)
        if dt == 0:
            duplicate_ts += 1

    gap_threshold = expected_interval_s * gap_factor
    gap_count = sum(1 for dt in intervals_s if dt > gap_threshold)
    negative_or_zero_intervals = sum(1 for dt in intervals_s if dt <= 0)

    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None
    duration_h = ((last_ts - first_ts).total_seconds() / 3600.0) if first_ts and last_ts else 0.0

    missing_table = []
    for col in columns:
        miss = missing_counts[col]
        missing_table.append(
            {
                "column": col,
                "missing_count": miss,
                "missing_pct": _pct(miss, total_rows),
            }
        )

    missing_table.sort(key=lambda x: x["missing_count"], reverse=True)

    report = {
        "path": str(csv_path),
        "rows": total_rows,
        "columns": len(columns),
        "first_timestamp_utc": first_ts.isoformat() if first_ts else None,
        "last_timestamp_utc": last_ts.isoformat() if last_ts else None,
        "duration_hours": duration_h,
        "invalid_timestamp_rows": invalid_ts_rows,
        "duplicate_timestamp_rows": duplicate_ts,
        "interval_stats_seconds": {
            "expected_interval": expected_interval_s,
            "gap_threshold": gap_threshold,
            "count": len(intervals_s),
            "min": min(intervals_s) if intervals_s else None,
            "median": _quantile(intervals_s, 0.5),
            "p95": _quantile(intervals_s, 0.95),
            "max": max(intervals_s) if intervals_s else None,
            "gaps_over_threshold": gap_count,
            "non_positive_intervals": negative_or_zero_intervals,
        },
        "top_missing_columns": missing_table[:15],
    }
    return report


def print_report(report: dict) -> None:
    if report.get("rows", 0) == 0:
        print("Data Quality Report")
        print(f"- File: {report['path']}")
        print(f"- Rows: {report['rows']}")
        print(f"- Note: {report.get('message', '')}")
        return

    stats = report["interval_stats_seconds"]
    print("Data Quality Report")
    print(f"- File: {report['path']}")
    print(f"- Rows: {report['rows']}  |  Columns: {report['columns']}")
    print(
        f"- Window: {report['first_timestamp_utc']} -> {report['last_timestamp_utc']} "
        f"({report['duration_hours']:.2f}h)"
    )
    print(f"- Invalid timestamp rows: {report['invalid_timestamp_rows']}")
    print(f"- Duplicate timestamps: {report['duplicate_timestamp_rows']}")
    print(
        f"- Interval(s): min={stats['min']} median={stats['median']} p95={stats['p95']} max={stats['max']}"
    )
    print(
        f"- Gaps > {stats['gap_threshold']:.2f}s: {stats['gaps_over_threshold']} "
        f"(expected {stats['expected_interval']}s)"
    )
    print(f"- Non-positive intervals: {stats['non_positive_intervals']}")

    print("\nTop Missing Columns:")
    for row in report["top_missing_columns"]:
        print(
            f"- {row['column']}: {row['missing_count']} missing "
            f"({row['missing_pct']:.2f}%)"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate data quality report for feature CSV")
    parser.add_argument("--csv", default="data/phase3_features_with_pm.csv", help="Path to feature CSV")
    parser.add_argument("--expected-interval", type=float, default=1.0, help="Expected row interval seconds")
    parser.add_argument(
        "--gap-factor",
        type=float,
        default=2.5,
        help="Gap threshold multiplier over expected interval",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        return 1

    report = build_report(
        csv_path=csv_path,
        expected_interval_s=args.expected_interval,
        gap_factor=args.gap_factor,
    )
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

