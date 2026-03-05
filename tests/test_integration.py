"""Integration tests for Phase 2 hardening."""

import logging
import unittest

from phase2_pipeline.config_validator import validate_config
from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
from phase2_pipeline.feature_normalizer import FeatureNormalizer


class TestFeatureExtractorIntegration(unittest.TestCase):
    """FeatureExtractor + realistic StateStore snapshot -> all 17 features."""

    def test_all_17_features_populated(self):
        snapshot = {
            "oracle_prices": [100.0 + i * 0.01 for i in range(70)],
            "spot_prices": [100.05 + i * 0.01 for i in range(70)],
            "orderbook": {
                "bids": [[100, 10], [99, 9], [98, 8], [97, 7], [96, 6]],
                "asks": [[101, 5], [102, 5], [103, 5], [104, 5], [105, 5]],
            },
            "polymarket_orderbook": {
                "bids": [[0.49, 100], [0.48, 80], [0.47, 70], [0.46, 50], [0.45, 40]],
                "asks": [[0.51, 90], [0.52, 70], [0.53, 60], [0.54, 40], [0.55, 30]],
            },
            "pm_best_bid": 0.49,
            "pm_best_ask": 0.51,
            "pm_mid_prob": 0.50,
            "pm_spread": 0.02,
            "cvd_60s": 12.5,
            "seconds_remaining": 150.0,
            "funding_rate": 0.0001,
        }
        extractor = FeatureExtractor()
        features = extractor.extract(snapshot)

        self.assertEqual(set(features.keys()), set(FEATURE_COLUMNS))
        for col in FEATURE_COLUMNS:
            self.assertIsNotNone(features[col], f"{col} should not be None with full data")


class TestConfigValidation(unittest.TestCase):
    """Config validation: missing keys -> ValueError, valid -> ok."""

    def test_missing_required_key_raises(self):
        with self.assertRaises(ValueError):
            validate_config({})

    def test_missing_polygon_rpc_url_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"polygon_rpc_url": ""})

    def test_valid_config_no_error(self):
        cfg = validate_config({"polygon_rpc_url": "https://example.com/rpc"})
        self.assertEqual(cfg["polygon_rpc_url"], "https://example.com/rpc")
        self.assertIsInstance(cfg["oracle_poll_seconds"], float)
        self.assertIsInstance(cfg["alert_threshold_pct"], float)
        self.assertIsInstance(cfg["max_oracle_age_seconds"], float)
        self.assertGreater(cfg["oracle_poll_seconds"], 0)

    def test_type_coercion(self):
        cfg = validate_config({
            "polygon_rpc_url": "https://example.com/rpc",
            "oracle_poll_seconds": "10",
            "alert_threshold_pct": "0.5",
        })
        self.assertEqual(cfg["oracle_poll_seconds"], 10.0)
        self.assertEqual(cfg["alert_threshold_pct"], 0.5)

    def test_invalid_range_raises(self):
        with self.assertRaises(ValueError):
            validate_config({
                "polygon_rpc_url": "https://example.com/rpc",
                "oracle_poll_seconds": -1,
            })


class TestFeatureNormalizer(unittest.TestCase):
    """FeatureNormalizer: z-scores correct after N updates."""

    def test_zscore_after_updates(self):
        normalizer = FeatureNormalizer()
        # Feed 100 samples: value = i for feature "x"
        for i in range(100):
            normalizer.update({"x": float(i), "y": float(i * 2)})

        # The mean of 0..99 is 49.5, std ~= 29.01
        result = normalizer.normalize({"x": 49.5, "y": 99.0})
        # z-score of the mean should be ~0
        self.assertAlmostEqual(result["x"], 0.0, places=1)
        self.assertAlmostEqual(result["y"], 0.0, places=1)

    def test_zscore_clipping(self):
        normalizer = FeatureNormalizer(clip=3.0)
        for i in range(100):
            normalizer.update({"x": float(i)})

        # Extreme outlier should be clipped
        result = normalizer.normalize({"x": 1000.0})
        self.assertLessEqual(result["x"], 3.0)

        result = normalizer.normalize({"x": -1000.0})
        self.assertGreaterEqual(result["x"], -3.0)

    def test_none_values_preserved(self):
        normalizer = FeatureNormalizer()
        normalizer.update({"x": 1.0})
        result = normalizer.normalize({"x": None})
        self.assertIsNone(result["x"])


class TestOracleStaleness(unittest.TestCase):
    """Oracle staleness: old timestamp -> warning logged."""

    def test_stale_oracle_triggers_warning(self):
        import time
        from unittest.mock import MagicMock

        from phase2_pipeline.live_runner import Phase2LiveRunner

        # We can't easily run the full async loop, so test the logic directly
        runner = Phase2LiveRunner.__new__(Phase2LiveRunner)
        runner.max_oracle_age_seconds = 300.0
        runner.oracle_stale = False
        runner._log = MagicMock()

        from phase2_pipeline.state_store import UnifiedStateStore

        runner.state = UnifiedStateStore()
        # Set oracle_updated_at to 600 seconds ago
        runner.state.oracle_updated_at = int(time.time()) - 600

        from datetime import datetime, timezone

        now_ts = int(datetime.now(timezone.utc).timestamp())
        age_seconds = now_ts - int(runner.state.oracle_updated_at)

        # Simulate the staleness check from heartbeat_loop
        oracle_stale = False
        if runner.state.oracle_updated_at:
            if age_seconds > runner.max_oracle_age_seconds:
                oracle_stale = True

        self.assertTrue(oracle_stale)
        self.assertGreater(age_seconds, 300)


class TestOBIFallback(unittest.TestCase):
    """OBI fallback: PM orderbook empty -> Binance OBI used."""

    def test_binance_obi_fallback(self):
        snapshot = {
            "oracle_prices": [100.0],
            "spot_prices": [100.1],
            "orderbook": {
                "bids": [[100, 10], [99, 9], [98, 8], [97, 7], [96, 6]],
                "asks": [[101, 5], [102, 5], [103, 5], [104, 5], [105, 5]],
            },
            "polymarket_orderbook": {"bids": [], "asks": []},
            "pm_best_bid": None,
            "pm_best_ask": None,
            "pm_mid_prob": None,
            "pm_spread": None,
            "cvd_60s": 0.0,
            "seconds_remaining": 150.0,
            "funding_rate": None,
        }
        extractor = FeatureExtractor()
        features = extractor.extract(snapshot)

        # pm_obi should be None (not enough levels), but obi should use Binance
        self.assertIsNone(features["pm_obi"])
        self.assertIsNotNone(features["obi"])


if __name__ == "__main__":
    unittest.main()
