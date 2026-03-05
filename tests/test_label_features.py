import csv
import os
import tempfile
import unittest

from label_features import (
    assign_buckets,
    export_labeled,
    label_buckets,
    load_feature_csv,
)


def _make_row(ts_iso: str, spot_price: str, oracle_price: str = "68000.0") -> dict:
    """Helper to create a minimal feature row."""
    return {
        "timestamp_utc": ts_iso,
        "oracle_round_id": "123",
        "oracle_price_usd": oracle_price,
        "spot_price_usd": spot_price,
        "oracle_lag_pct": "0.01",
        "momentum_30s": "0.0",
        "momentum_60s": "0.0",
        "slope": "0.0",
        "sigma_short": "0.0",
        "sigma_long": "0.0",
        "sigma_ratio": "1.0",
        "obi": "0.5",
        "cvd_60s": "0.0",
        "tau": "0.5",
        "tau_sq": "0.25",
        "funding_rate": "0.0001",
        "pm_best_bid": "0.5",
        "pm_best_ask": "0.5",
        "pm_mid_prob": "0.5",
        "pm_spread": "0.01",
        "pm_obi": "0.5",
    }


# Bucket boundary: use values actually aligned to 300-second boundaries
# 1699999800 / 300 = 5666666.0 (exact)
_BUCKET_0_START = 1699999800  # 2023-11-14T22:10:00 UTC
_BUCKET_1_START = 1700000100  # next 5-min bucket: +300s


def _ts(epoch: int) -> str:
    """Convert epoch to ISO-8601 UTC string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )


class TestAssignBuckets(unittest.TestCase):
    def test_same_bucket(self):
        """Rows within the same 5-min window go to the same bucket."""
        rows = [
            _make_row(_ts(_BUCKET_0_START), "100.0"),
            _make_row(_ts(_BUCKET_0_START + 60), "101.0"),
            _make_row(_ts(_BUCKET_0_START + 120), "102.0"),
        ]
        buckets = assign_buckets(rows)
        self.assertEqual(len(buckets), 1)
        self.assertIn(_BUCKET_0_START, buckets)
        self.assertEqual(len(buckets[_BUCKET_0_START]), 3)

    def test_different_buckets(self):
        """Rows crossing a 5-min boundary go to different buckets."""
        rows = [
            _make_row(_ts(_BUCKET_0_START), "100.0"),
            _make_row(_ts(_BUCKET_1_START), "101.0"),
        ]
        buckets = assign_buckets(rows)
        self.assertEqual(len(buckets), 2)
        self.assertIn(_BUCKET_0_START, buckets)
        self.assertIn(_BUCKET_1_START, buckets)


class TestLabelBuckets(unittest.TestCase):
    def _make_bucket_rows(self, start_epoch, start_price, end_price, n=15):
        """Generate n rows for a single bucket with linear price interpolation."""
        rows = []
        for i in range(n):
            t = start_epoch + i
            price = start_price + (end_price - start_price) * i / (n - 1)
            rows.append(_make_row(_ts(t), f"{price:.2f}"))
        return rows

    def test_label_up(self):
        """Price rises → label=1."""
        rows_b0 = self._make_bucket_rows(_BUCKET_0_START, 100.0, 105.0)
        rows_b1 = self._make_bucket_rows(_BUCKET_1_START, 105.0, 110.0)
        # Need a third bucket so b1 isn't dropped as last
        _BUCKET_2_START = _BUCKET_1_START + 300
        rows_b2 = self._make_bucket_rows(_BUCKET_2_START, 110.0, 112.0)

        all_rows = rows_b0 + rows_b1 + rows_b2
        buckets = assign_buckets(all_rows)
        labeled = label_buckets(buckets, min_ticks=1)

        self.assertEqual(len(labeled), 2)
        self.assertEqual(labeled[0]["label"], 1)
        self.assertEqual(labeled[1]["label"], 1)

    def test_label_down(self):
        """Price falls → label=0."""
        rows_b0 = self._make_bucket_rows(_BUCKET_0_START, 105.0, 100.0)
        # Dummy bucket so b0 isn't dropped
        rows_b1 = self._make_bucket_rows(_BUCKET_1_START, 100.0, 99.0)

        all_rows = rows_b0 + rows_b1
        buckets = assign_buckets(all_rows)
        labeled = label_buckets(buckets, min_ticks=1)

        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0]["label"], 0)

    def test_flat_price_labels_down(self):
        """Price unchanged → label=0 (not strictly greater)."""
        rows_b0 = self._make_bucket_rows(_BUCKET_0_START, 100.0, 100.0)
        rows_b1 = self._make_bucket_rows(_BUCKET_1_START, 100.0, 100.0)

        buckets = assign_buckets(rows_b0 + rows_b1)
        labeled = label_buckets(buckets, min_ticks=1)

        self.assertEqual(labeled[0]["label"], 0)

    def test_last_bucket_excluded(self):
        """The last bucket is always dropped (potentially incomplete)."""
        rows = self._make_bucket_rows(_BUCKET_0_START, 100.0, 105.0, n=20)
        buckets = assign_buckets(rows)
        self.assertEqual(len(buckets), 1)

        labeled = label_buckets(buckets, min_ticks=1)
        self.assertEqual(len(labeled), 0)

    def test_min_ticks_filter(self):
        """Buckets with fewer than min_ticks are dropped."""
        rows_b0 = self._make_bucket_rows(_BUCKET_0_START, 100.0, 105.0, n=5)
        rows_b1 = self._make_bucket_rows(_BUCKET_1_START, 105.0, 110.0, n=20)
        _BUCKET_2_START = _BUCKET_1_START + 300
        rows_b2 = self._make_bucket_rows(_BUCKET_2_START, 110.0, 112.0, n=20)

        buckets = assign_buckets(rows_b0 + rows_b1 + rows_b2)
        labeled = label_buckets(buckets, min_ticks=10)

        # b0 has only 5 ticks → dropped; b1 has 20 → kept; b2 is last → dropped
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0]["bucket_start_ts"], _BUCKET_1_START)

    def test_first_tick_features_used(self):
        """The representative features come from the first tick in the bucket."""
        rows_b0 = [
            _make_row(_ts(_BUCKET_0_START), "100.0"),
            _make_row(_ts(_BUCKET_0_START + 1), "101.0"),
            _make_row(_ts(_BUCKET_0_START + 2), "102.0"),
        ]
        rows_b1 = [_make_row(_ts(_BUCKET_1_START + i), "110.0") for i in range(3)]

        buckets = assign_buckets(rows_b0 + rows_b1)
        labeled = label_buckets(buckets, min_ticks=1)

        self.assertEqual(labeled[0]["spot_price_usd"], "100.0")
        self.assertEqual(labeled[0]["end_price"], 102.0)

    def test_extra_fields_present(self):
        """Output rows have bucket_start_ts, end_price, and label."""
        rows_b0 = self._make_bucket_rows(_BUCKET_0_START, 100.0, 105.0, n=10)
        rows_b1 = self._make_bucket_rows(_BUCKET_1_START, 105.0, 110.0, n=10)

        buckets = assign_buckets(rows_b0 + rows_b1)
        labeled = label_buckets(buckets, min_ticks=1)

        row = labeled[0]
        self.assertIn("bucket_start_ts", row)
        self.assertIn("end_price", row)
        self.assertIn("label", row)


class TestLoadFeatureCSV(unittest.TestCase):
    def test_skips_empty_spot_price(self):
        """Rows with empty spot_price_usd are skipped."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_utc", "spot_price_usd", "oracle_price_usd"])
            writer.writerow(["2024-01-01T00:00:00", "", "100.0"])
            writer.writerow(["2024-01-01T00:00:01", "101.0", "100.0"])
            writer.writerow(["2024-01-01T00:00:02", "", "100.0"])
            path = f.name

        try:
            rows = load_feature_csv(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["spot_price_usd"], "101.0")
        finally:
            os.unlink(path)


class TestExportLabeled(unittest.TestCase):
    def test_roundtrip(self):
        """Export and re-read produces same data."""
        labeled = [
            {
                "timestamp_utc": "2024-01-01T00:00:00",
                "spot_price_usd": "100.0",
                "bucket_start_ts": 1700000000,
                "end_price": 105.0,
                "label": 1,
            }
        ]
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)

        try:
            export_labeled(labeled, path)
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["label"], "1")
            self.assertEqual(rows[0]["end_price"], "105.0")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
