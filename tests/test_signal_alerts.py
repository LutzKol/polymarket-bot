"""Tests for trade-signal alerts (Discord/Telegram notifier wrapper)."""

from __future__ import annotations

import unittest

from phase2_pipeline.signal_alerts import (
    SignalAlertConfig,
    SignalAlertNotifier,
    format_trade_signal_alert,
    is_actionable_trade_signal,
)
from phase2_pipeline.trade_signal import TradeSignal


def _signal(
    *,
    ts: str = "2026-02-22T12:01:00Z",
    direction: str = "UP",
    size: float = 10.0,
    risk_ok: bool = True,
    reason: str = "",
) -> TradeSignal:
    return TradeSignal(
        timestamp=ts,
        direction=direction,
        model_probability=0.61,
        market_probability=0.50,
        ev=0.04,
        kelly_fraction=0.03,
        suggested_size_usdc=size,
        risk_checks_passed=risk_ok,
        reason=reason,
        bankroll_usdc=1000.0,
        brier_score=0.20,
    )


class TestSignalAlerts(unittest.TestCase):
    def test_actionable_signal_true(self):
        self.assertTrue(is_actionable_trade_signal(_signal()))

    def test_actionable_signal_false_for_none(self):
        self.assertFalse(is_actionable_trade_signal(_signal(direction="NONE")))

    def test_format_contains_core_fields(self):
        msg = format_trade_signal_alert(_signal())
        self.assertIn("ACTIONABLE", msg)
        self.assertIn("p_model=", msg)
        self.assertIn("size=$10.00", msg)

    def test_notifier_disabled_without_credentials(self):
        cfg = SignalAlertConfig(enabled=True, provider="discord", discord_webhook_url="")
        n = SignalAlertNotifier(cfg)
        self.assertFalse(n.is_enabled())

    def test_notifier_sends_and_dedupes_by_bucket(self):
        sent: list[tuple[str, str]] = []
        t = {"now": 1000.0}

        def fake_sender(provider: str, msg: str) -> None:
            sent.append((provider, msg))

        def fake_time() -> float:
            return t["now"]

        cfg = SignalAlertConfig(
            enabled=True,
            provider="discord",
            discord_webhook_url="https://example.test/webhook",
            actionable_only=True,
            min_interval_seconds=0.0,
            dedupe_by_bucket=True,
        )
        n = SignalAlertNotifier(cfg, sender=fake_sender, time_fn=fake_time)

        ok1, reason1 = n.notify(_signal(ts="2026-02-22T12:01:00Z", direction="UP"))
        ok2, reason2 = n.notify(_signal(ts="2026-02-22T12:03:00Z", direction="UP"))
        ok3, reason3 = n.notify(_signal(ts="2026-02-22T12:03:00Z", direction="DOWN"))

        self.assertEqual((ok1, reason1), (True, "sent"))
        self.assertEqual((ok2, reason2), (False, "duplicate_bucket"))
        self.assertEqual((ok3, reason3), (True, "sent"))
        self.assertEqual(len(sent), 2)

    def test_notifier_throttle(self):
        sent: list[tuple[str, str]] = []
        t = {"now": 1000.0}

        def fake_sender(provider: str, msg: str) -> None:
            sent.append((provider, msg))

        def fake_time() -> float:
            return t["now"]

        cfg = SignalAlertConfig(
            enabled=True,
            provider="telegram",
            telegram_bot_token="bot",
            telegram_chat_id="chat",
            actionable_only=True,
            min_interval_seconds=60.0,
            dedupe_by_bucket=False,
        )
        n = SignalAlertNotifier(cfg, sender=fake_sender, time_fn=fake_time)
        self.assertEqual(n.notify(_signal(ts="2026-02-22T12:01:00Z")), (True, "sent"))
        self.assertEqual(n.notify(_signal(ts="2026-02-22T12:06:00Z")), (False, "throttled"))
        t["now"] = 1061.0
        self.assertEqual(n.notify(_signal(ts="2026-02-22T12:06:00Z")), (True, "sent"))
        self.assertEqual(len(sent), 2)

    def test_notifier_skips_non_actionable_when_configured(self):
        sent: list[tuple[str, str]] = []
        cfg = SignalAlertConfig(
            enabled=True,
            provider="discord",
            discord_webhook_url="https://example.test/webhook",
            actionable_only=True,
        )
        n = SignalAlertNotifier(cfg, sender=lambda p, m: sent.append((p, m)))
        self.assertEqual(n.notify(_signal(direction="NONE")), (False, "not_actionable"))
        self.assertEqual(len(sent), 0)


if __name__ == "__main__":
    unittest.main()

