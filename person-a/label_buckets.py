#!/usr/bin/env python3
"""Label feature rows by 5-min bucket outcome (oracle price up or down).

For each 5-min bucket, compares oracle_price at bucket start vs end.
Label 1 = price went UP, Label 0 = price went DOWN or unchanged.

Usage:
    python3 label_buckets.py --input data/phase3_features_training.csv --output data/labeled_full.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def label(input_path: str, output_path: str) -> None:
    with open(input_path, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        print("No rows found.")
        sys.exit(1)

    # Group rows by 5-min bucket
    buckets: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        ts = row.get("timestamp_utc", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            bucket_id = int(dt.timestamp()) // 300
            buckets[bucket_id].append(row)
        except (ValueError, OSError):
            continue

    sorted_bucket_ids = sorted(buckets.keys())
    print(f"Total rows: {len(rows)}")
    print(f"Total 5-min buckets: {len(sorted_bucket_ids)}")

    # For each bucket, determine label from oracle price at start vs end
    bucket_labels: dict[int, int] = {}
    skipped = 0
    for bid in sorted_bucket_ids:
        bucket_rows = buckets[bid]
        try:
            start_price = float(bucket_rows[0]["oracle_price_usd"])
            end_price = float(bucket_rows[-1]["oracle_price_usd"])
        except (ValueError, KeyError):
            skipped += 1
            continue
        bucket_labels[bid] = 1 if end_price > start_price else 0

    print(f"Labeled buckets: {len(bucket_labels)} (skipped {skipped})")
    ups = sum(v for v in bucket_labels.values())
    downs = len(bucket_labels) - ups
    print(f"Distribution: {ups} UP / {downs} DOWN ({ups / len(bucket_labels) * 100:.1f}% UP)")

    # Write output: only rows from labeled buckets, with label column added
    out_fields = list(fieldnames) + ["bucket_id", "label"]
    labeled_rows = 0
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        for bid in sorted_bucket_ids:
            if bid not in bucket_labels:
                continue
            label_val = bucket_labels[bid]
            for row in buckets[bid]:
                row["bucket_id"] = str(bid)
                row["label"] = str(label_val)
                writer.writerow(row)
                labeled_rows += 1

    print(f"Written {labeled_rows} labeled rows to {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Label feature CSV by 5-min bucket outcome")
    parser.add_argument("--input", default="data/phase3_features_training.csv", help="Input feature CSV")
    parser.add_argument("--output", default="data/labeled_full.csv", help="Output labeled CSV")
    args = parser.parse_args()
    label(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
