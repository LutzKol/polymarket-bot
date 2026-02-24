"""Tests for Phase 4 EV-Engine components."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from phase2_pipeline.ev_engine import (
    EVCalculator,
    KellySizer,
    ModelLoader,
    RiskManager,
    evaluate_signal,
)
from phase2_pipeline.trade_signal import TradeSignal


class TestEVCalculator(unittest.TestCase):
    def setUp(self):
        self.calc = EVCalculator(ev_threshold=0.02, fee=0.02)

    def test_positive_ev_up(self):
        ev, direction = self.calc.calculate(model_prob=0.65, market_prob=0.50)
        self.assertEqual(direction, "UP")
        self.assertGreater(ev, 0.02)

    def test_positive_ev_down(self):
        # Model thinks UP is only 0.30, so DOWN side has edge
        ev, direction = self.calc.calculate(model_prob=0.30, market_prob=0.50)
        self.assertEqual(direction, "DOWN")
        self.assertGreater(ev, 0.02)

    def test_no_edge_returns_none(self):
        ev, direction = self.calc.calculate(model_prob=0.51, market_prob=0.50)
        self.assertEqual(direction, "NONE")

    def test_threshold_boundary(self):
        # Find a prob that gives EV just at threshold
        calc = EVCalculator(ev_threshold=0.10, fee=0.02)
        ev, direction = calc.calculate(model_prob=0.55, market_prob=0.50)
        # EV_yes = 0.55 * 0.98 - 0.50 = 0.039 < 0.10
        self.assertEqual(direction, "NONE")

    def test_zero_fee(self):
        calc = EVCalculator(ev_threshold=0.02, fee=0.0)
        ev, direction = calc.calculate(model_prob=0.65, market_prob=0.50)
        self.assertEqual(direction, "UP")
        # EV_yes = 0.65 * 1.0 - 0.50 = 0.15
        self.assertAlmostEqual(ev, 0.15, places=4)


class TestKellySizer(unittest.TestCase):
    def setUp(self):
        self.sizer = KellySizer(max_fraction=0.02)

    def test_positive_edge_with_cap(self):
        kelly, size = self.sizer.size(
            model_prob=0.65, market_prob=0.50, direction="UP",
            bankroll=1000.0, fee=0.02,
        )
        self.assertGreater(kelly, 0)
        self.assertLessEqual(size, 1000.0 * 0.02)
        self.assertGreater(size, 0)

    def test_negative_edge_returns_zero(self):
        kelly, size = self.sizer.size(
            model_prob=0.50, market_prob=0.55, direction="UP",
            bankroll=1000.0, fee=0.02,
        )
        self.assertEqual(kelly, 0.0)
        self.assertEqual(size, 0.0)

    def test_none_direction_returns_zero(self):
        kelly, size = self.sizer.size(
            model_prob=0.65, market_prob=0.50, direction="NONE",
            bankroll=1000.0, fee=0.02,
        )
        self.assertEqual(kelly, 0.0)
        self.assertEqual(size, 0.0)

    def test_zero_bankroll_returns_zero(self):
        kelly, size = self.sizer.size(
            model_prob=0.65, market_prob=0.50, direction="UP",
            bankroll=0.0, fee=0.02,
        )
        self.assertEqual(size, 0.0)


class TestRiskManager(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager(max_consecutive_losses=3, brier_gate=0.24, max_fraction=0.02)

    def test_all_clear(self):
        passed, reason = self.rm.check_all(
            model_output=0.6, oracle_stale=False, size_usdc=10, bankroll=1000,
        )
        self.assertTrue(passed)
        self.assertEqual(reason, "")

    def test_no_model_output(self):
        passed, reason = self.rm.check_all(
            model_output=None, oracle_stale=False, size_usdc=10, bankroll=1000,
        )
        self.assertFalse(passed)
        self.assertIn("model_output_none", reason)

    def test_oracle_stale(self):
        passed, reason = self.rm.check_all(
            model_output=0.6, oracle_stale=True, size_usdc=10, bankroll=1000,
        )
        self.assertFalse(passed)
        self.assertIn("oracle_stale", reason)

    def test_three_consecutive_losses(self):
        for _ in range(3):
            self.rm.record_outcome(won=False, predicted_prob=0.6, actual=0.0)
        passed, reason = self.rm.check_all(
            model_output=0.6, oracle_stale=False, size_usdc=10, bankroll=1000,
        )
        self.assertFalse(passed)
        self.assertIn("consecutive_losses", reason)

    def test_win_resets_counter(self):
        # Use well-calibrated predictions so brier gate isn't triggered
        rm = RiskManager(max_consecutive_losses=3, brier_gate=0.24, max_fraction=0.02)
        rm.record_outcome(won=False, predicted_prob=0.4, actual=0.0)
        rm.record_outcome(won=False, predicted_prob=0.4, actual=0.0)
        rm.record_outcome(won=True, predicted_prob=0.6, actual=1.0)
        self.assertEqual(rm.consecutive_losses, 0)
        passed, _ = rm.check_all(
            model_output=0.6, oracle_stale=False, size_usdc=10, bankroll=1000,
        )
        self.assertTrue(passed)

    def test_brier_gate(self):
        # Push brier scores that average > 0.24
        for _ in range(10):
            self.rm.record_outcome(won=True, predicted_prob=0.0, actual=1.0)
        # Brier = (0.0 - 1.0)^2 = 1.0, average = 1.0 > 0.24
        passed, reason = self.rm.check_all(
            model_output=0.6, oracle_stale=False, size_usdc=10, bankroll=1000,
        )
        self.assertFalse(passed)
        self.assertIn("brier_gate_exceeded", reason)

    def test_multiple_reasons(self):
        for _ in range(3):
            self.rm.record_outcome(won=False, predicted_prob=0.0, actual=1.0)
        passed, reason = self.rm.check_all(
            model_output=None, oracle_stale=True, size_usdc=10, bankroll=1000,
        )
        self.assertFalse(passed)
        self.assertIn("model_output_none", reason)
        self.assertIn("oracle_stale", reason)
        self.assertIn("consecutive_losses", reason)
        self.assertIn("brier_gate_exceeded", reason)


class TestModelLoader(unittest.TestCase):
    def test_json_weights_predict(self):
        # bias=0, w1=1.0 for a single feature
        data = {"weights": [0.0, 1.0]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            loader = ModelLoader(path, feature_columns=["x"])
            prob = loader.predict_proba({"x": 0.0})
            self.assertIsNotNone(prob)
            self.assertAlmostEqual(prob, 0.5, places=4)

            prob_pos = loader.predict_proba({"x": 2.0})
            self.assertGreater(prob_pos, 0.5)
        finally:
            os.unlink(path)

    def test_missing_features_returns_none(self):
        data = {"weights": [0.0, 1.0, -0.5]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            loader = ModelLoader(path, feature_columns=["a", "b"])
            result = loader.predict_proba({"a": 1.0})  # missing "b"
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            ModelLoader("/nonexistent/model.json", feature_columns=["x"])


class TestTradeSignal(unittest.TestCase):
    def test_csv_columns_match_to_dict_keys(self):
        signal = TradeSignal(
            timestamp="2026-01-01T00:00:00Z",
            direction="UP",
            model_probability=0.6,
            market_probability=0.5,
            ev=0.1,
            kelly_fraction=0.05,
            suggested_size_usdc=10.0,
            risk_checks_passed=True,
            reason="",
            bankroll_usdc=1000.0,
            brier_score=None,
        )
        self.assertEqual(list(signal.to_dict().keys()), TradeSignal.csv_columns())


class TestEvaluateSignal(unittest.TestCase):
    def test_full_pipeline(self):
        data = {"weights": [0.0, 1.0, -0.5, 0.2]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            model = ModelLoader(path, feature_columns=["a", "b", "c"])
            rm = RiskManager()
            ev_calc = EVCalculator()
            kelly = KellySizer()

            signal = evaluate_signal(
                features={"a": 2.0, "b": -1.0, "c": 0.5},
                model=model,
                market_prob=0.50,
                bankroll=1000.0,
                risk_manager=rm,
                ev_calculator=ev_calc,
                kelly_sizer=kelly,
            )
            self.assertIsInstance(signal, TradeSignal)
            self.assertIn(signal.direction, ("UP", "DOWN", "NONE"))
            self.assertGreater(signal.model_probability, 0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
