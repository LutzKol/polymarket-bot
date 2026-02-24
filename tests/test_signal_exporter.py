"""Tests for offline signal exporter (feature CSV -> trade_signals.csv)."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from phase2_pipeline.signal_exporter import export_signals_from_feature_csv
from phase2_pipeline.trade_signal import TradeSignal


class TestSignalExporter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.feature_csv = self.root / "features.csv"
        self.model_json = self.root / "model.json"
        self.out_csv = self.root / "trade_signals.csv"

        # Weights: bias + 3 feature weights
        self.model_json.write_text(
            json.dumps({"weights": [0.0, 2.0, 0.0, 0.0]}),
            encoding="utf-8",
        )

        fieldnames = [
            "timestamp_utc",
            "oracle_lag_pct",
            "sigma_short",
            "momentum_30s",
            "pm_mid_prob",
        ]
        rows = [
            {
                "timestamp_utc": "2026-02-22T12:00:00Z",
                "oracle_lag_pct": "",
                "sigma_short": "0.1",
                "momentum_30s": "0.2",
                "pm_mid_prob": "0.50",
            },
            {
                "timestamp_utc": "2026-02-22T12:00:01Z",
                "oracle_lag_pct": "0.05",
                "sigma_short": "0.11",
                "momentum_30s": "0.21",
                "pm_mid_prob": "0.52",
            },
            {
                "timestamp_utc": "2026-02-22T12:00:02Z",
                "oracle_lag_pct": "0.06",
                "sigma_short": "0.12",
                "momentum_30s": "0.22",
                "pm_mid_prob": "",
            },
        ]
        with self.feature_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exports_signals_and_counts_model_none(self):
        report = export_signals_from_feature_csv(
            input_csv=self.feature_csv,
            output_csv=self.out_csv,
            model_path=str(self.model_json),
            model_feature_columns=["oracle_lag_pct", "sigma_short", "momentum_30s"],
            bankroll_usdc=1000.0,
            ev_threshold=0.0,
        )

        self.assertEqual(report["rows_total"], 3)
        self.assertEqual(report["rows_written"], 3)
        # First row has missing oracle_lag_pct -> model output none
        self.assertEqual(report["rows_model_none"], 1)

        with self.out_csv.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual(list(rows[0].keys()), TradeSignal.csv_columns())
        self.assertEqual(rows[1]["timestamp"], "2026-02-22T12:00:01Z")
        # third row falls back to market_prob=0.5 because pm_mid_prob empty
        self.assertEqual(float(rows[2]["market_probability"]), 0.5)


if __name__ == "__main__":
    unittest.main()

