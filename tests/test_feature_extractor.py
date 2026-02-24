import unittest

from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor


class TestFeatureExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = FeatureExtractor()

    def test_extract_returns_all_columns(self):
        snapshot = {
            "oracle_prices": [100.0 + i * 0.1 for i in range(70)],
            "spot_prices": [100.1 + i * 0.1 for i in range(70)],
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
            "cvd_60s": 1.234,
            "seconds_remaining": 150.0,
            "funding_rate": 0.0001,
        }
        out = self.extractor.extract(snapshot)
        self.assertEqual(set(out.keys()), set(FEATURE_COLUMNS))
        self.assertIsNotNone(out["oracle_lag_pct"])
        self.assertIsNotNone(out["momentum_30s"])
        self.assertIsNotNone(out["momentum_60s"])
        self.assertIsNotNone(out["slope"])
        self.assertIsNotNone(out["sigma_short"])
        self.assertIsNotNone(out["sigma_long"])
        self.assertIsNotNone(out["sigma_ratio"])
        self.assertIsNotNone(out["obi"])
        self.assertEqual(out["cvd_60s"], 1.234)
        self.assertAlmostEqual(out["tau"], 0.5, places=8)
        self.assertAlmostEqual(out["tau_sq"], 0.25, places=8)
        self.assertAlmostEqual(out["funding_rate"], 0.0001, places=8)
        self.assertAlmostEqual(out["pm_best_bid"], 0.49, places=8)
        self.assertAlmostEqual(out["pm_best_ask"], 0.51, places=8)
        self.assertAlmostEqual(out["pm_mid_prob"], 0.5, places=8)
        self.assertAlmostEqual(out["pm_spread"], 0.02, places=8)
        self.assertIsNotNone(out["pm_obi"])

    def test_missing_data_returns_none(self):
        out = self.extractor.extract(
            {
                "oracle_prices": [],
                "spot_prices": [],
                "orderbook": {"bids": [], "asks": []},
                "cvd_60s": None,
                "seconds_remaining": None,
                "funding_rate": None,
            }
        )
        for key in FEATURE_COLUMNS:
            self.assertIsNone(out[key], msg=f"{key} should be None for empty input")


if __name__ == "__main__":
    unittest.main()
