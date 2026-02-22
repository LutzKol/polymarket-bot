#!/usr/bin/env python3
"""Labeling pipeline for model training.

Reads feature CSVs produced by feature_exporter.py, groups rows into
5-minute buckets (matching Polymarket BTC 5-Min Up/Down resolution),
and assigns a binary label: 1 if price went up, 0 otherwise.
"""

import argparse
import csv
import sys
from datetime import datetime, timezone


def load_feature_csv(path: str) -> list[dict]:
    """Load feature CSV, skipping rows with empty spot_price_usd."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("spot_price_usd"):
                continue
            rows.append(row)
    return rows


def _unix_ts(iso_str: str) -> float:
    """Convert ISO-8601 timestamp to UNIX epoch seconds."""
    dt = datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc)
    return dt.timestamp()


def assign_buckets(rows: list[dict]) -> dict[int, list[dict]]:
    """Group rows into 5-minute buckets based on timestamp_utc.

    Bucket key = floor(unix_timestamp / 300) * 300.
    """
    buckets: dict[int, list[dict]] = {}
    for row in rows:
        ts = _unix_ts(row["timestamp_utc"])
        bucket_key = int(ts // 300) * 300
        buckets.setdefault(bucket_key, []).append(row)
    return buckets


def label_buckets(
    buckets: dict[int, list[dict]], min_ticks: int = 10
) -> list[dict]:
    """Label each completed bucket.

    - Drops the last (potentially incomplete) bucket.
    - Drops buckets with fewer than *min_ticks* rows.
    - Uses the first tick's features as representative features.
    - Label = 1 if last price > first price, else 0.

    Returns a list of dicts ready for CSV export.
    """
    if not buckets:
        return []

    sorted_keys = sorted(buckets.keys())
    # Drop last bucket (incomplete)
    completed_keys = sorted_keys[:-1]

    labeled: list[dict] = []
    for key in completed_keys:
        ticks = buckets[key]
        if len(ticks) < min_ticks:
            continue

        first_tick = ticks[0]
        last_tick = ticks[-1]
        first_price = float(first_tick["spot_price_usd"])
        end_price = float(last_tick["spot_price_usd"])
        label = 1 if end_price > first_price else 0

        row = dict(first_tick)
        row["bucket_start_ts"] = key
        row["end_price"] = end_price
        row["label"] = label
        labeled.append(row)

    return labeled


def export_labeled(rows: list[dict], output_path: str) -> None:
    """Write labeled rows to CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_stats(
    total_buckets: int,
    labeled_rows: list[dict],
    dropped_incomplete: int,
    dropped_min_ticks: int,
) -> None:
    """Print labeling statistics to stdout."""
    n_labeled = len(labeled_rows)
    up = sum(1 for r in labeled_rows if r["label"] == 1)
    down = n_labeled - up

    print(f"Total buckets:      {total_buckets}")
    print(f"Labeled buckets:    {n_labeled}")
    print(f"  Up  (label=1):    {up}")
    print(f"  Down(label=0):    {down}")
    print(f"Dropped (last/inc): {dropped_incomplete}")
    print(f"Dropped (min-ticks):{dropped_min_ticks}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Label feature CSVs for model training."
    )
    parser.add_argument("--input", required=True, help="Input feature CSV path")
    parser.add_argument(
        "--output", required=True, help="Output labeled CSV path"
    )
    parser.add_argument(
        "--min-ticks",
        type=int,
        default=10,
        help="Minimum ticks per bucket (default: 10)",
    )
    args = parser.parse_args()

    rows = load_feature_csv(args.input)
    if not rows:
        print("No valid rows found in input CSV.")
        sys.exit(1)

    buckets = assign_buckets(rows)
    total_buckets = len(buckets)

    # Count drops
    sorted_keys = sorted(buckets.keys())
    dropped_incomplete = 1 if len(sorted_keys) > 0 else 0
    completed_keys = sorted_keys[:-1] if sorted_keys else []
    dropped_min_ticks = sum(
        1 for k in completed_keys if len(buckets[k]) < args.min_ticks
    )

    labeled = label_buckets(buckets, min_ticks=args.min_ticks)
    export_labeled(labeled, args.output)

    print_stats(total_buckets, labeled, dropped_incomplete, dropped_min_ticks)
    print(f"\nLabeled data written to: {args.output}")


if __name__ == "__main__":
    main()
