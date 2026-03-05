import unittest

from phase2_pipeline.features import calculate_cvd, calculate_obi, update_cvd


class TestCalculateOBI(unittest.TestCase):
    def test_balanced_orderbook_returns_zero(self):
        orderbook = {
            "bids": [[100, 10], [99, 10], [98, 10], [97, 10], [96, 10]],
            "asks": [[101, 10], [102, 10], [103, 10], [104, 10], [105, 10]],
        }
        obi = calculate_obi(orderbook)
        self.assertIsNotNone(obi)
        self.assertAlmostEqual(obi, 0.0, places=8)

    def test_buy_pressure_returns_positive_obi(self):
        orderbook = {
            "bids": [[100, 20], [99, 20], [98, 20], [97, 20], [96, 20]],
            "asks": [[101, 10], [102, 10], [103, 10], [104, 10], [105, 10]],
        }
        obi = calculate_obi(orderbook)
        self.assertIsNotNone(obi)
        self.assertGreater(obi, 0.0)

    def test_less_than_5_levels_returns_none(self):
        orderbook = {
            "bids": [[100, 10], [99, 10], [98, 10], [97, 10]],
            "asks": [[101, 10], [102, 10], [103, 10], [104, 10]],
        }
        self.assertIsNone(calculate_obi(orderbook))


class TestCVD(unittest.TestCase):
    def test_update_cvd_buy_and_sell(self):
        cvd = 0.0
        cvd = update_cvd(cvd, "buy", 3.0)
        cvd = update_cvd(cvd, "sell", 1.5)
        self.assertAlmostEqual(cvd, 1.5, places=8)

    def test_calculate_cvd_from_trade_list(self):
        trades = [
            {"side": "buy", "qty": 2.5},
            {"side": "sell", "qty": 1.0},
            {"side": "buy", "qty": 0.5},
        ]
        self.assertAlmostEqual(calculate_cvd(trades), 2.0, places=8)

    def test_update_cvd_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            update_cvd(0.0, "unknown", 1.0)


if __name__ == "__main__":
    unittest.main()

