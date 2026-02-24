import unittest

from phase2_pipeline.polymarket_client import (
    extract_btc_5m_market_candidates_from_event_detail,
    next_5m_boundary_timestamps,
    parse_polymarket_book,
    select_yes_token_id_from_market,
)


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


class TestPolymarketResolverHelpers(unittest.TestCase):
    def test_extract_candidates_decodes_string_lists(self):
        detail = {
            "markets": [
                {
                    "clobTokenIds": '["111","222"]',
                    "outcomes": '["Up","Down"]',
                }
            ]
        }
        out = extract_btc_5m_market_candidates_from_event_detail(detail)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["token_ids"], ["111", "222"])
        self.assertEqual(out[0]["outcomes"], ["Up", "Down"])

    def test_select_yes_prefers_up_outcome(self):
        market = {"token_ids": ["aaa", "bbb"], "outcomes": ["Down", "Up"]}
        self.assertEqual(select_yes_token_id_from_market(market), "bbb")

    def test_select_yes_falls_back_first(self):
        market = {"token_ids": ["aaa", "bbb"], "outcomes": ["Foo", "Bar"]}
        self.assertEqual(select_yes_token_id_from_market(market), "aaa")

    def test_next_5m_boundary_timestamps_count(self):
        out = next_5m_boundary_timestamps(3)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(isinstance(x, int) for x in out))
        self.assertLess(out[0], out[1])


if __name__ == "__main__":
    unittest.main()
