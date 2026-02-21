import unittest

from phase2_pipeline.polymarket_client import parse_polymarket_book


class TestPolymarketBookParser(unittest.TestCase):
    def test_parse_dict_levels_and_best_prices(self):
        payload = {
            "bids": [
                {"price": "0.49", "size": "100"},
                {"price": "0.48", "size": "80"},
            ],
            "asks": [
                {"price": "0.51", "size": "90"},
                {"price": "0.52", "size": "70"},
            ],
            "best_bid": "0.49",
            "best_ask": "0.51",
        }
        out = parse_polymarket_book(payload)
        self.assertEqual(len(out["bids"]), 2)
        self.assertEqual(len(out["asks"]), 2)
        self.assertAlmostEqual(out["best_bid"], 0.49, places=8)
        self.assertAlmostEqual(out["best_ask"], 0.51, places=8)
        self.assertAlmostEqual(out["implied_mid_prob"], 0.50, places=8)
        self.assertAlmostEqual(out["spread"], 0.02, places=8)

    def test_parse_list_levels_with_percent_prices(self):
        payload = {
            "bids": [[49, 100], [48, 80]],
            "asks": [[51, 90], [52, 70]],
        }
        out = parse_polymarket_book(payload)
        self.assertAlmostEqual(out["best_bid"], 0.49, places=8)
        self.assertAlmostEqual(out["best_ask"], 0.51, places=8)
        self.assertAlmostEqual(out["implied_mid_prob"], 0.50, places=8)

    def test_invalid_payload_returns_empty_values(self):
        out = parse_polymarket_book({"bids": "bad", "asks": None})
        self.assertEqual(out["bids"], [])
        self.assertEqual(out["asks"], [])
        self.assertIsNone(out["best_bid"])
        self.assertIsNone(out["best_ask"])
        self.assertIsNone(out["implied_mid_prob"])
        self.assertIsNone(out["spread"])


if __name__ == "__main__":
    unittest.main()

