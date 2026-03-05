"""Tests for Phase 5 paper trading and fill simulation."""

from __future__ import annotations

import unittest

from phase2_pipeline.ev_engine import RiskManager
from phase2_pipeline.paper_trading import (
    FillConfig,
    FillSimulator,
    PaperRiskLimits,
    PaperTrade,
    PaperTradingEngine,
    polymarket_variable_fee_rate,
)
from phase2_pipeline.trade_signal import TradeSignal


def _signal(
    *,
    direction: str = "UP",
    market_probability: float = 0.50,
    size_usdc: float = 100.0,
    risk_checks_passed: bool = True,
    model_probability: float = 0.62,
    ev: float = 0.05,
    ts: str = "2026-02-22T12:00:00Z",
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


class TestFillSimulator(unittest.TestCase):
    def test_up_uses_ask_plus_penalty(self):
        fill = FillSimulator(
            FillConfig(half_spread_bps=10, slippage_bps=5, latency_bps=5)
        )
        # base ask=0.51, penalty=20 bps => +0.00102
        price = fill.entry_fill_price(
            "UP", market_probability=0.50, pm_best_bid=0.49, pm_best_ask=0.51
        )
        self.assertAlmostEqual(price, 0.51102, places=6)

    def test_down_uses_inverse_bid_plus_penalty(self):
        fill = FillSimulator(
            FillConfig(half_spread_bps=10, slippage_bps=10, latency_bps=0)
        )
        # NO ask ~= 1 - 0.49 = 0.51; penalty 20bps => +0.00102
        price = fill.entry_fill_price(
            "DOWN", market_probability=0.50, pm_best_bid=0.49, pm_best_ask=0.51
        )
        self.assertAlmostEqual(price, 0.51102, places=6)

    def test_clamps_extreme_price(self):
        fill = FillSimulator(FillConfig(half_spread_bps=1000, max_price=0.999))
        price = fill.entry_fill_price("UP", market_probability=0.999, pm_best_ask=0.999)
        self.assertLess(price, 1.0)

    def test_variable_fee_matches_research_peak(self):
        self.assertAlmostEqual(polymarket_variable_fee_rate(0.50), 0.015625, places=8)

    def test_variable_entry_fee_rate_from_fill_price(self):
        fill = FillSimulator(FillConfig(use_variable_fees=True))
        self.assertAlmostEqual(fill.entry_fee_rate(0.5), 0.015625, places=8)


class TestPaperTradingEngine(unittest.TestCase):
    def test_skip_non_trade_signal(self):
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trade = engine.open_trade(_signal(direction="NONE"), event_id="evt-1")
        self.assertIsNone(trade)
        self.assertEqual(engine.open_count, 0)

    def test_skip_failed_risk_checks(self):
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0)
        trade = engine.open_trade(
            _signal(direction="UP", risk_checks_passed=False), event_id="evt-1"
        )
        self.assertIsNone(trade)

    def test_open_and_resolve_yes_win_updates_bankroll_and_risk(self):
        rm = RiskManager()
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig(entry_fee_rate=0.01, exit_fee_rate=0.01)),
            risk_manager=rm,
        )
        trade = engine.open_trade(_signal(direction="UP", size_usdc=100.0), event_id="evt-1")
        self.assertIsInstance(trade, PaperTrade)
        self.assertEqual(engine.open_count, 1)
        self.assertLess(engine.cash_usdc, 1000.0)

        closed = engine.resolve_trade(trade.trade_id, outcome_up=True, closed_at="2026-02-22T12:05:00Z")
        self.assertEqual(closed.status, "CLOSED")
        self.assertTrue(closed.won)
        self.assertGreater(closed.pnl_usdc, 0.0)
        self.assertEqual(engine.open_count, 0)
        self.assertEqual(engine.closed_count, 1)
        self.assertGreater(engine.cash_usdc, 1000.0)
        self.assertEqual(rm.consecutive_losses, 0)
        self.assertIsNotNone(rm.rolling_brier)

    def test_open_and_resolve_no_loss_increments_consecutive_losses(self):
        rm = RiskManager()
        engine = PaperTradingEngine(starting_bankroll_usdc=1000.0, risk_manager=rm)
        trade = engine.open_trade(_signal(direction="DOWN", size_usdc=50.0), event_id="evt-2")
        self.assertIsNotNone(trade)
        closed = engine.resolve_trade(trade.trade_id, outcome_up=True)
        self.assertFalse(closed.won)
        self.assertLess(closed.pnl_usdc, 0.0)
        self.assertEqual(rm.consecutive_losses, 1)

    def test_summary_fields_present(self):
        engine = PaperTradingEngine(starting_bankroll_usdc=500.0)
        t1 = engine.open_trade(_signal(direction="UP", size_usdc=50.0), event_id="evt-a")
        engine.resolve_trade(t1.trade_id, outcome_up=False)
        t2 = engine.open_trade(_signal(direction="DOWN", size_usdc=50.0), event_id="evt-b")
        engine.resolve_trade(t2.trade_id, outcome_up=False)

        summary = engine.summary()
        self.assertEqual(summary["closed_trades"], 2)
        self.assertIn("max_drawdown", summary)
        self.assertIn("total_pnl_usdc", summary)
        self.assertLessEqual(summary["win_rate"], 1.0)

    def test_variable_fee_applied_to_entry(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            fill_simulator=FillSimulator(FillConfig(use_variable_fees=True)),
        )
        trade = engine.open_trade(
            _signal(direction="UP", size_usdc=100.0, market_probability=0.50),
            event_id="evt-varfee",
            pm_best_bid=0.49,
            pm_best_ask=0.51,
        )
        self.assertIsNotNone(trade)
        # Variable fee around 1.56% for ~0.51 entry, so > $1
        self.assertGreater(trade.entry_fee_usdc, 1.0)

    def test_max_trades_per_day_blocks_second_trade(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            risk_limits=PaperRiskLimits(max_trades_per_day=1),
        )
        t1 = engine.open_trade(_signal(ts="2026-02-22T12:00:00Z", size_usdc=10.0), event_id="evt-1")
        self.assertIsNotNone(t1)
        t2 = engine.open_trade(_signal(ts="2026-02-22T12:01:00Z", size_usdc=10.0), event_id="evt-2")
        self.assertIsNone(t2)
        self.assertEqual(engine.last_reject_reason, "max_trades_per_day")

    def test_daily_loss_stop_blocks_after_large_loss(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=100.0,
            risk_limits=PaperRiskLimits(max_daily_loss_fraction=0.08),
        )
        t1 = engine.open_trade(_signal(size_usdc=9.0, ts="2026-02-22T12:00:00Z"), event_id="evt-1")
        self.assertIsNotNone(t1)
        # Lose the YES bet -> realized loss ~= $9 > 8% of day-start bankroll ($8).
        engine.resolve_trade(t1.trade_id, outcome_up=False, closed_at="2026-02-22T12:05:00Z")
        t2 = engine.open_trade(_signal(size_usdc=5.0, ts="2026-02-22T12:06:00Z"), event_id="evt-2")
        self.assertIsNone(t2)
        self.assertEqual(engine.last_reject_reason, "daily_loss_stop")

    def test_cooldown_blocks_immediate_next_trade_after_loss_streak(self):
        engine = PaperTradingEngine(
            starting_bankroll_usdc=1000.0,
            risk_limits=PaperRiskLimits(
                cooldown_after_consecutive_losses=2,
                cooldown_minutes=30,
            ),
        )
        t1 = engine.open_trade(_signal(size_usdc=10.0, ts="2026-02-22T12:00:00Z"), event_id="evt-1")
        engine.resolve_trade(t1.trade_id, outcome_up=False, closed_at="2026-02-22T12:05:00Z")
        t2 = engine.open_trade(_signal(size_usdc=10.0, ts="2026-02-22T12:06:00Z"), event_id="evt-2")
        engine.resolve_trade(t2.trade_id, outcome_up=False, closed_at="2026-02-22T12:10:00Z")

        blocked = engine.open_trade(
            _signal(size_usdc=10.0, ts="2026-02-22T12:15:00Z"),
            event_id="evt-3",
        )
        self.assertIsNone(blocked)
        self.assertEqual(engine.last_reject_reason, "cooldown_active")

        # After cooldown window passes, trade is allowed again.
        allowed = engine.open_trade(
            _signal(size_usdc=10.0, ts="2026-02-22T12:41:00Z"),
            event_id="evt-4",
        )
        self.assertIsNotNone(allowed)


if __name__ == "__main__":
    unittest.main()
