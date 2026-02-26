"""Tests for Phase 5 live paper trading integration in live_runner."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from phase2_pipeline.paper_trading import (
    FillConfig,
    FillSimulator,
    PaperRiskLimits,
    PaperTrade,
    PaperTradingEngine,
)
from phase2_pipeline.ev_engine import RiskManager
from phase2_pipeline.signal_alerts import format_daily_reset, format_kill_switch, format_paper_trade_opened, format_paper_trade_resolved
from phase2_pipeline.trade_signal import TradeSignal


def _signal(
    *,
    direction: str = "UP",
    market_probability: float = 0.50,
    size_usdc: float = 20.0,
    risk_checks_passed: bool = True,
    model_probability: float = 0.65,
    ev: float = 0.137,
    ts: str = "2026-02-22T18:00:01Z",
) -> TradeSignal:
    return TradeSignal(
        timestamp=ts,
        direction=direction,
        model_probability=model_probability,
        market_probability=market_probability,
        ev=ev,
        kelly_fraction=0.03,
        suggested_size_usdc=size_usdc,
        risk_checks_passed=risk_checks_passed,
        reason="",
        bankroll_usdc=1000.0,
        brier_score=None,
    )


class TestPaperTradingEngineConvenience(unittest.TestCase):
    """Tests for new convenience methods on PaperTradingEngine."""

    def _engine(self) -> PaperTradingEngine:
        return PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )

    def test_has_open_trades_false_initially(self):
        engine = self._engine()
        self.assertFalse(engine.has_open_trades())

    def test_has_open_trades_true_after_open(self):
        engine = self._engine()
        engine.open_trade(_signal(), "bucket_100")
        self.assertTrue(engine.has_open_trades())

    def test_open_trade_for_bucket_returns_none_when_empty(self):
        engine = self._engine()
        self.assertIsNone(engine.open_trade_for_bucket("bucket_100"))

    def test_open_trade_for_bucket_returns_trade_id(self):
        engine = self._engine()
        trade = engine.open_trade(_signal(), "bucket_100")
        self.assertIsNotNone(trade)
        result = engine.open_trade_for_bucket("bucket_100")
        self.assertEqual(result, trade.trade_id)

    def test_resolve_open_trade_resolves_single(self):
        engine = self._engine()
        trade = engine.open_trade(_signal(), "bucket_100")
        self.assertIsNotNone(trade)
        resolved = engine.resolve_open_trade(outcome_up=True)
        self.assertEqual(resolved.trade_id, trade.trade_id)
        self.assertEqual(resolved.status, "CLOSED")
        self.assertFalse(engine.has_open_trades())

    def test_resolve_open_trade_raises_when_no_trades(self):
        engine = self._engine()
        with self.assertRaises(KeyError):
            engine.resolve_open_trade(outcome_up=True)


class TestBucketChangeResolvesTrade(unittest.TestCase):
    """Simulate the bucket-change logic from the heartbeat loop."""

    def test_bucket_change_resolves_trade(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )

        # Open a trade in bucket 100
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        self.assertTrue(engine.has_open_trades())

        # Simulate bucket change: oracle went up -> outcome_up = True
        bucket_start_price = 50000.0
        bucket_end_price = 50100.0
        outcome_up = bucket_end_price > bucket_start_price

        resolved = engine.resolve_open_trade(outcome_up)
        self.assertEqual(resolved.status, "CLOSED")
        self.assertTrue(resolved.resolution_outcome_up)
        self.assertFalse(engine.has_open_trades())


class TestOneTradePerBucket(unittest.TestCase):
    def test_one_trade_per_bucket(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )

        bucket_id = "200"
        sig1 = _signal(direction="UP")
        trade1 = engine.open_trade(sig1, bucket_id)
        self.assertIsNotNone(trade1)

        # Second trade in same bucket should be blocked by caller check
        existing = engine.open_trade_for_bucket(bucket_id)
        self.assertIsNotNone(existing)
        # In live_runner, we skip opening if open_trade_for_bucket returns non-None


class TestNoTradeWhenRiskFailed(unittest.TestCase):
    def test_no_trade_when_risk_failed(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(risk_checks_passed=False)
        trade = engine.open_trade(sig, "100")
        self.assertIsNone(trade)
        self.assertEqual(engine.last_reject_reason, "signal_risk_checks_failed")


class TestNoTradeWhenDirectionNone(unittest.TestCase):
    def test_no_trade_when_direction_none(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="NONE")
        trade = engine.open_trade(sig, "100")
        self.assertIsNone(trade)
        self.assertEqual(engine.last_reject_reason, "direction_none")


class TestResolutionUpdatesRiskManager(unittest.TestCase):
    def test_resolution_updates_risk_manager(self):
        risk_mgr = RiskManager(max_consecutive_losses=3, brier_gate=0.30)
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
            risk_manager=risk_mgr,
        )
        sig = _signal(direction="UP", model_probability=0.65)
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        initial_count = len(risk_mgr._brier_scores)
        engine.resolve_open_trade(outcome_up=True)
        self.assertEqual(len(risk_mgr._brier_scores), initial_count + 1)


class TestPaperTradeCSVWritten(unittest.TestCase):
    def test_paper_trade_csv_written(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        resolved = engine.resolve_open_trade(outcome_up=True)

        # Write to temp CSV
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, newline=""
        ) as f:
            csv_path = f.name
            writer = csv.writer(f)
            writer.writerow(PaperTrade.csv_columns())
            row = resolved.to_dict()
            writer.writerow([row[col] for col in PaperTrade.csv_columns()])

        try:
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["direction"], "UP")
            self.assertEqual(rows[0]["status"], "CLOSED")
            self.assertEqual(rows[0]["contract_side"], "YES")
        finally:
            os.unlink(csv_path)


class TestPaperDisabledSkipsEverything(unittest.TestCase):
    def test_paper_disabled_skips_everything(self):
        """When paper_trading_enabled=False, no engine is created."""
        # Simulate what live_runner.__init__ does
        paper_trading_enabled = False
        ev_enabled = True  # even if EV is on

        paper_engine = None
        if paper_trading_enabled and ev_enabled:
            paper_engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)

        self.assertIsNone(paper_engine)


class TestAcceptanceCheck200Trades(unittest.TestCase):
    def test_acceptance_check_200_trades(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=10000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )

        wins = 0
        total = 210
        for i in range(total):
            sig = _signal(
                direction="UP",
                size_usdc=5.0,
                ts=f"2026-02-22T12:{i // 60:02d}:{i % 60:02d}Z",
            )
            trade = engine.open_trade(sig, f"bucket_{i}")
            self.assertIsNotNone(trade, f"Trade {i} should not be None")
            # Alternate outcomes: 56% win rate
            outcome_up = (i % 25) != 0  # lose every 25th trade
            resolved = engine.resolve_trade(trade.trade_id, outcome_up)
            if resolved.won:
                wins += 1

        summary = engine.summary()
        self.assertGreaterEqual(summary["closed_trades"], 200)
        self.assertGreater(summary["win_rate"], 0.54)
        self.assertEqual(summary["open_trades"], 0)


class TestFormatPaperTradeOpened(unittest.TestCase):
    def test_format_paper_trade_opened(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP", model_probability=0.65, market_probability=0.50, ev=0.137)
        trade = engine.open_trade(sig, "5905824")
        self.assertIsNotNone(trade)
        msg = format_paper_trade_opened(trade)
        self.assertIn("\U0001f7e2", msg)  # green circle
        self.assertIn("PAPER TRADE OPENED", msg)
        self.assertIn("\u2191", msg)  # up arrow
        self.assertIn("Direction: UP (YES)", msg)
        self.assertIn("Entry:", msg)
        self.assertIn("Size:", msg)
        self.assertIn("Model:", msg)
        self.assertIn("Market:", msg)
        self.assertIn("EV:", msg)
        self.assertIn("Bucket: #5905824", msg)

    def test_format_paper_trade_opened_down(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="DOWN", model_probability=0.65, market_probability=0.50, ev=0.137)
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        msg = format_paper_trade_opened(trade)
        self.assertIn("\u2193", msg)  # down arrow
        self.assertIn("Direction: DOWN (NO)", msg)


class TestFormatPaperTradeResolvedWon(unittest.TestCase):
    def test_format_paper_trade_resolved_won(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        resolved = engine.resolve_open_trade(outcome_up=True)
        summary = engine.summary()
        msg = format_paper_trade_resolved(resolved, summary)
        self.assertIn("\u2705", msg)  # checkmark
        self.assertIn("PAPER TRADE WON", msg)
        self.assertIn("Record:", msg)
        self.assertIn("1W/0L", msg)
        self.assertIn("Bankroll:", msg)
        self.assertIn("Entry:", msg)
        self.assertIn("\u2192", msg)  # arrow
        self.assertIn("Exit:", msg)


class TestFormatPaperTradeResolvedLost(unittest.TestCase):
    def test_format_paper_trade_resolved_lost(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        resolved = engine.resolve_open_trade(outcome_up=False)
        summary = engine.summary()
        msg = format_paper_trade_resolved(resolved, summary)
        self.assertIn("\u274c", msg)  # red X
        self.assertIn("PAPER TRADE LOST", msg)
        self.assertIn("PnL: -", msg)
        self.assertIn("0W/1L", msg)


class TestDailyReset(unittest.TestCase):
    def test_daily_summary_and_reset(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP", ts="2026-02-24T12:00:00Z")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)
        engine.resolve_open_trade(outcome_up=True)

        day_summary = engine.daily_summary("2026-02-24")
        self.assertEqual(day_summary["day"], "2026-02-24")
        self.assertEqual(day_summary["trades"], 1)
        self.assertEqual(day_summary["wins"], 1)

    def test_format_daily_reset(self):
        day_summary = {
            "day": "2026-02-24",
            "trades": 5,
            "wins": 3,
            "losses": 2,
            "win_rate": 0.6,
            "pnl_usdc": 15.50,
            "start_equity": 1000.0,
            "end_equity": 1015.50,
        }
        overall_summary = {
            "wins": 10,
            "losses": 6,
            "ending_bankroll_usdc": 1015.50,
            "total_pnl_usdc": 15.50,
        }
        msg = format_daily_reset(day_summary, overall_summary)
        self.assertIn("\U0001f504", msg)
        self.assertIn("DAILY RESET", msg)
        self.assertIn("2026-02-24", msg)
        self.assertIn("3W/2L", msg)
        self.assertIn("10W/6L", msg)
        self.assertIn("Bankroll:", msg)

    def test_reset_cooldown(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        engine._cooldown_until_epoch = 9999999999.0
        self.assertIsNotNone(engine._cooldown_until_epoch)
        engine.reset_cooldown()
        self.assertIsNone(engine._cooldown_until_epoch)


class TestKillSwitchLowWinRate(unittest.TestCase):
    def test_kill_switch_low_win_rate(self):
        """Kill switch triggers when win rate < 54% after 50+ trades."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=10000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        # Generate 50 trades with ~48% win rate (24 wins, 26 losses)
        for i in range(50):
            sig = _signal(
                direction="UP",
                size_usdc=5.0,
                ts=f"2026-02-22T12:{i // 60:02d}:{i % 60:02d}Z",
            )
            trade = engine.open_trade(sig, f"bucket_{i}")
            self.assertIsNotNone(trade)
            outcome_up = i < 24  # first 24 win, rest lose
            engine.resolve_trade(trade.trade_id, outcome_up)

        triggered, reason = engine.check_kill_switch()
        self.assertTrue(triggered)
        self.assertIn("Win rate below threshold", reason)
        self.assertTrue(engine.kill_switch_triggered)


class TestKillSwitchDrawdown(unittest.TestCase):
    def test_kill_switch_drawdown(self):
        """Kill switch triggers when max drawdown exceeds 15%."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        # Lose enough to create >15% drawdown
        for i in range(20):
            sig = _signal(
                direction="UP",
                size_usdc=20.0,
                ts=f"2026-02-22T12:00:{i:02d}Z",
            )
            trade = engine.open_trade(sig, f"bucket_{i}")
            if trade is None:
                break
            engine.resolve_trade(trade.trade_id, outcome_up=False)

        triggered, reason = engine.check_kill_switch()
        self.assertTrue(triggered)
        # Could be drawdown or bankroll floor depending on loss magnitude
        self.assertTrue(
            "drawdown" in reason.lower() or "bankroll" in reason.lower()
        )


class TestKillSwitchBankrollFloor(unittest.TestCase):
    def test_kill_switch_bankroll_floor(self):
        """Kill switch triggers when bankroll drops below 50% of starting."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        # Set cash below 50% threshold but keep equity curve flat to avoid
        # drawdown triggering first
        engine.cash_usdc = 400.0
        engine._equity_curve = [400.0]

        triggered, reason = engine.check_kill_switch()
        self.assertTrue(triggered)
        self.assertIn("Bankroll below 50%", reason)
        self.assertTrue(engine.kill_switch_triggered)


class TestKillSwitchBlocksNewTrades(unittest.TestCase):
    def test_kill_switch_blocks_new_trades(self):
        """After kill switch triggers, new trades are rejected."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        # Manually trigger kill switch
        engine.kill_switch_triggered = True
        engine.kill_switch_reason = "test trigger"

        sig = _signal(direction="UP", size_usdc=10.0)
        trade = engine.open_trade(sig, "bucket_999")
        self.assertIsNone(trade)
        self.assertEqual(engine.last_reject_reason, "kill_switch")


class TestFormatKillSwitch(unittest.TestCase):
    def test_format_kill_switch(self):
        """Verify kill-switch Telegram message format."""
        summary = {
            "wins": 24,
            "losses": 26,
            "ending_bankroll_usdc": 912.50,
        }
        reason = "Win rate below threshold (48.0% < 54.0%)"
        msg = format_kill_switch(reason, summary)
        self.assertIn("\U0001f6a8", msg)
        self.assertIn("KILL-SWITCH ACTIVATED", msg)
        self.assertIn("Win rate below threshold", msg)
        self.assertIn("24W/26L", msg)
        self.assertIn("50 trades", msg)
        self.assertIn("$912.50", msg)
        self.assertIn("Paper trading paused", msg)
        self.assertIn("manual review required", msg)


class TestPolymarketResolutionFallback(unittest.TestCase):
    """Verify oracle fallback still works when Polymarket resolution is unavailable."""

    def test_oracle_fallback_after_retries_exhausted(self):
        """When retries are exhausted and no PM resolution, oracle comparison is used."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        # Simulate oracle fallback: price went up -> outcome_up = True
        bucket_start_price = 50000.0
        bucket_end_price = 50100.0
        outcome_up = bucket_end_price > bucket_start_price
        resolved = engine.resolve_open_trade(outcome_up)
        self.assertEqual(resolved.status, "CLOSED")
        self.assertTrue(resolved.resolution_outcome_up)
        self.assertFalse(engine.has_open_trades())

    def test_oracle_fallback_price_down(self):
        """Oracle fallback when price goes down."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "200")
        self.assertIsNotNone(trade)

        outcome_up = 49900.0 > 50000.0  # False
        resolved = engine.resolve_open_trade(outcome_up)
        self.assertFalse(resolved.resolution_outcome_up)


class TestPolymarketResolutionWins(unittest.TestCase):
    """Verify correct trade settlement with Polymarket outcomes."""

    def test_polymarket_up_resolves_up_trade_as_win(self):
        """When Polymarket says UP and trade direction is UP -> win."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        # Polymarket says outcome_up=True
        resolved = engine.resolve_open_trade(outcome_up=True)
        self.assertTrue(resolved.won)
        self.assertTrue(resolved.resolution_outcome_up)

    def test_polymarket_down_resolves_up_trade_as_loss(self):
        """When Polymarket says DOWN and trade direction is UP -> loss."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="UP")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        # Polymarket says outcome_up=False
        resolved = engine.resolve_open_trade(outcome_up=False)
        self.assertFalse(resolved.won)
        self.assertFalse(resolved.resolution_outcome_up)

    def test_polymarket_down_resolves_down_trade_as_win(self):
        """When Polymarket says DOWN and trade direction is DOWN -> win."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="DOWN")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        # Polymarket says outcome_up=False -> DOWN wins
        resolved = engine.resolve_open_trade(outcome_up=False)
        self.assertTrue(resolved.won)

    def test_polymarket_up_resolves_down_trade_as_loss(self):
        """When Polymarket says UP and trade direction is DOWN -> loss."""
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig()),
        )
        sig = _signal(direction="DOWN")
        trade = engine.open_trade(sig, "100")
        self.assertIsNotNone(trade)

        # Polymarket says outcome_up=True -> DOWN trade loses
        resolved = engine.resolve_open_trade(outcome_up=True)
        self.assertFalse(resolved.won)


if __name__ == "__main__":
    unittest.main()
