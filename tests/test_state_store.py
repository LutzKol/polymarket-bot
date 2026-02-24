import unittest
from datetime import datetime, timedelta

from phase2_pipeline.state_store import UnifiedStateStore


class TestUnifiedStateStore(unittest.TestCase):
    def test_snapshot_contains_expected_keys(self):
        store = UnifiedStateStore(history_size=120)
        store.update_oracle(price=68000.0, round_id=123, updated_at=1700000000)
        store.update_spot(price=68010.0)
        store.update_orderbook(
            bids=[[68000, 1], [67990, 1], [67980, 1], [67970, 1], [67960, 1]],
            asks=[[68020, 1], [68030, 1], [68040, 1], [68050, 1], [68060, 1]],
        )
        snapshot = store.snapshot(seconds_remaining=42.0)

        self.assertIn("oracle_prices", snapshot)
        self.assertIn("spot_prices", snapshot)
        self.assertIn("orderbook", snapshot)
        self.assertIn("cvd_60s", snapshot)
        self.assertEqual(snapshot["seconds_remaining"], 42.0)

    def test_cvd_window_uses_recent_trades_only(self):
        store = UnifiedStateStore(history_size=120)
        now = datetime.utcnow()

        store.add_trade("buy", 3.0, ts=now - timedelta(seconds=10))
        store.add_trade("sell", 1.0, ts=now - timedelta(seconds=5))
        store.add_trade("buy", 2.0, ts=now - timedelta(seconds=90))

        cvd_60 = store.cvd_window(window_seconds=60, now=now)
        self.assertAlmostEqual(cvd_60, 2.0, places=8)


if __name__ == "__main__":
    unittest.main()

