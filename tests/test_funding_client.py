import unittest

from phase2_pipeline.funding_client import parse_binance_premium_index


class TestFundingClient(unittest.TestCase):
    def test_parse_last_funding_rate(self):
        payload = {"lastFundingRate": "0.00010000"}
        rate = parse_binance_premium_index(payload)
        self.assertAlmostEqual(rate, 0.0001, places=10)

    def test_parse_missing_field_raises(self):
        with self.assertRaises(ValueError):
            parse_binance_premium_index({})


if __name__ == "__main__":
    unittest.main()
