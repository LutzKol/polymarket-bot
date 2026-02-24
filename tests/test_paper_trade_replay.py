"""Tests for Phase 5 replay runner (signals + labels -> paper trades)."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from phase2_pipeline.paper_trade_replay import load_labels_by_bucket, replay_signals, write_trades_csv
from phase2_pipeline.paper_trading import PaperRiskLimits, PaperTradingEngine
from phase2_pipeline.trade_signal import TradeSignal


class TestPaperTradeReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.signals_csv = self.root / "trade_signals.csv"
        self.labels_csv = self.root / "labeled_training.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_signals(self, rows: list[dict]) -> None:
        with self.signals_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TradeSignal.csv_columns())
            writer.writeheader()
            writer.writerows(rows)

    def _write_labels(self, rows: list[dict]) -> None:
        fieldnames = ["bucket_start_ts", "label", "pm_best_bid", "pm_best_ask"]
        with self.labels_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _signal_row(timestamp: str, direction: str = "UP", ev: float = 0.05) -> dict:
        return {
            "timestamp": timestamp,
            "direction": direction,
            "model_probability": "0.62",
            "market_probability": "0.50",
            "ev": str(ev),
            "kelly_fraction": "0.03",
            "suggested_size_usdc": "50.0",
            "risk_checks_passed": "True",
            "reason": "",
            "bankroll_usdc": "1000.0",
            "brier_score": "",
        }

    def test_load_labels_by_bucket(self):
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "1", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
                {"bucket_start_ts": "1771680900", "label": "0", "pm_best_bid": "0.48", "pm_best_ask": "0.52"},
            ]
        )
        labels = load_labels_by_bucket(self.labels_csv)
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[1771680900]["label"], "1")

    def test_replay_matches_bucket_and_resolves_trade(self):
        # 2026-02-21T13:37:20Z -> bucket 1771680900
        self._write_signals([self._signal_row("2026-02-21T13:37:20Z", direction="UP")])
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "1", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
            ]
        )
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trades, replay_stats = replay_signals(self.signals_csv, self.labels_csv, engine)

        self.assertEqual(replay_stats["rows_signals_total"], 1)
        self.assertEqual(replay_stats["rows_signals_opened"], 1)
        self.assertEqual(len(trades), 1)
        self.assertTrue(trades[0].won)
        self.assertEqual(trades[0].event_id, "bucket_1771680900")

    def test_one_trade_per_bucket_skips_duplicates(self):
        self._write_signals(
            [
                self._signal_row("2026-02-21T13:37:20Z", direction="UP"),
                self._signal_row("2026-02-21T13:37:50Z", direction="DOWN"),
            ]
        )
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "0", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
            ]
        )
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trades, replay_stats = replay_signals(self.signals_csv, self.labels_csv, engine)
        self.assertEqual(len(trades), 1)
        self.assertEqual(replay_stats["rows_signals_skipped_duplicate_bucket"], 1)

    def test_min_ev_filter_skips_low_ev(self):
        self._write_signals([self._signal_row("2026-02-21T13:37:20Z", direction="UP", ev=0.01)])
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "1", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
            ]
        )
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trades, replay_stats = replay_signals(
            self.signals_csv, self.labels_csv, engine, min_ev=0.02
        )
        self.assertEqual(len(trades), 0)
        self.assertEqual(replay_stats["rows_signals_skipped_not_tradeable"], 1)

    def test_write_trades_csv(self):
        self._write_signals([self._signal_row("2026-02-21T13:37:20Z", direction="UP")])
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "1", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
            ]
        )
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trades, _ = replay_signals(self.signals_csv, self.labels_csv, engine)

        out_csv = self.root / "paper_trades.csv"
        write_trades_csv(trades, out_csv)
        with out_csv.open() as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 1)
        self.assertIn("pnl_usdc", rows[0])

    def test_replay_counts_policy_rejects(self):
        self._write_signals(
            [
                self._signal_row("2026-02-21T13:37:20Z", direction="UP"),
                self._signal_row("2026-02-21T13:37:50Z", direction="UP"),
            ]
        )
        self._write_labels(
            [
                {"bucket_start_ts": "1771680900", "label": "1", "pm_best_bid": "0.49", "pm_best_ask": "0.51"},
            ]
        )
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            risk_limits=PaperRiskLimits(max_trades_per_day=1),
        )
        trades, replay_stats = replay_signals(
            self.signals_csv,
            self.labels_csv,
            engine,
            one_trade_per_bucket=False,
        )
        self.assertEqual(len(trades), 1)
        self.assertEqual(replay_stats["rows_signals_skipped_max_trades_per_day"], 1)


if __name__ == "__main__":
    unittest.main()
