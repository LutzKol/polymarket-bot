"""Trade-signal alerts (Discord/Telegram) for actionable EV proposals."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.request import Request, urlopen

from phase2_pipeline.paper_trading import PaperTrade
from phase2_pipeline.trade_signal import TradeSignal


def _parse_iso_to_epoch(ts: str) -> float:
    value = (ts or "").strip()
    if value.endswith("Z"):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _bucket_5m(ts_epoch: float) -> int:
    return int(ts_epoch // 300) * 300


def is_actionable_trade_signal(signal: TradeSignal) -> bool:
    """True only for real trade proposals (not NONE / not blocked / nonzero size)."""
    return (
        signal.direction in ("UP", "DOWN")
        and bool(signal.risk_checks_passed)
        and float(signal.suggested_size_usdc) > 0
    )


def format_trade_signal_alert(signal: TradeSignal) -> str:
    """Render a compact text alert suitable for Discord/Telegram."""
    status = "ACTIONABLE" if is_actionable_trade_signal(signal) else "NON-ACTIONABLE"
    return (
        f"[{status}] {signal.direction} | ts={signal.timestamp} | "
        f"p_model={signal.model_probability:.4f} p_mkt={signal.market_probability:.4f} | "
        f"ev={signal.ev:.4f} | size=${signal.suggested_size_usdc:.2f} | "
        f"risk_ok={signal.risk_checks_passed} | reason={signal.reason or '-'}"
    )


def format_paper_trade_opened(trade: PaperTrade) -> str:
    """Rich emoji-formatted alert for a newly opened paper trade."""
    arrow = "\u2191" if trade.direction == "UP" else "\u2193"
    side = "YES" if trade.direction == "UP" else "NO"
    return (
        f"\U0001f7e2 PAPER TRADE OPENED\n"
        f"{arrow} Direction: {trade.direction} ({side})\n"
        f"Entry: {trade.entry_price:.4f} | Size: ${trade.size_usdc:.2f}\n"
        f"Model: {trade.model_probability * 100:.1f}% | "
        f"Market: {trade.market_probability_entry * 100:.1f}%\n"
        f"EV: {trade.ev_entry:+.3f} | Bucket: #{trade.event_id}"
    )


def format_paper_trade_resolved(trade: PaperTrade, summary: dict) -> str:
    """Rich emoji-formatted alert for a resolved paper trade."""
    if trade.won:
        header = "\u2705 PAPER TRADE WON"
    else:
        header = "\u274c PAPER TRADE LOST"
    arrow = "\u2191" if trade.direction == "UP" else "\u2193"
    side = "YES" if trade.direction == "UP" else "NO"
    exit_price = trade.exit_price if trade.exit_price is not None else 0.0
    pnl = trade.pnl_usdc if trade.pnl_usdc is not None else 0.0
    ret = trade.return_pct if trade.return_pct is not None else 0.0
    bankroll = summary.get("ending_bankroll_usdc", 0.0)
    wins = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0.0
    return (
        f"{header}\n"
        f"{arrow} Direction: {trade.direction} ({side})\n"
        f"Entry: {trade.entry_price:.4f} \u2192 Exit: {exit_price:.4f}\n"
        f"PnL: {pnl:+.2f} ({ret:+.1%})\n"
        f"Bankroll: ${bankroll:,.2f}\n"
        f"Record: {wins}W/{losses}L ({win_rate:.1f}%)"
    )


def format_daily_reset(day_summary: dict, overall_summary: dict) -> str:
    """Rich emoji-formatted alert for daily reset at 00:00 UTC."""
    day = day_summary["day"]
    trades = day_summary["trades"]
    wins = day_summary["wins"]
    losses = day_summary["losses"]
    win_rate = day_summary["win_rate"] * 100
    pnl = day_summary["pnl_usdc"]
    pnl_emoji = "\U0001f4c8" if pnl >= 0 else "\U0001f4c9"

    total_wins = overall_summary.get("wins", 0)
    total_losses = overall_summary.get("losses", 0)
    total_trades = total_wins + total_losses
    overall_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    bankroll = overall_summary.get("ending_bankroll_usdc", 0.0)
    total_pnl = overall_summary.get("total_pnl_usdc", 0.0)

    return (
        f"\U0001f504 DAILY RESET — {day}\n"
        f"\n"
        f"{pnl_emoji} Day: {wins}W/{losses}L ({trades} trades)\n"
        f"Day PnL: ${pnl:+,.2f} | Win Rate: {win_rate:.1f}%\n"
        f"\n"
        f"Overall: {total_wins}W/{total_losses}L ({total_trades} trades)\n"
        f"Total PnL: ${total_pnl:+,.2f} | Win Rate: {overall_wr:.1f}%\n"
        f"Bankroll: ${bankroll:,.2f}"
    )


def format_kill_switch(reason: str, summary: dict) -> str:
    """Format a kill-switch activation alert for Telegram/Discord."""
    wins = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    total = wins + losses
    bankroll = summary.get("ending_bankroll_usdc", 0.0)
    return (
        f"\U0001f6a8 KILL-SWITCH ACTIVATED\n"
        f"Reason: {reason}\n"
        f"Record: {wins}W/{losses}L ({total} trades)\n"
        f"Bankroll: ${bankroll:,.2f}\n"
        f"\u26a0\ufe0f Paper trading paused \u2014 manual review required"
    )


def _post_json(url: str, payload: dict, timeout_seconds: float = 10.0) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "polymarketbot-alerts/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout_seconds) as resp:
        # Consume body so urllib completes the request cleanly.
        resp.read()


def send_discord_webhook(webhook_url: str, message: str) -> None:
    _post_json(webhook_url, {"content": message})


def send_telegram_message(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    _post_json(url, {"chat_id": chat_id, "text": message})


@dataclass
class SignalAlertConfig:
    enabled: bool = False
    provider: str = ""  # "discord" | "telegram"
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    actionable_only: bool = True
    min_interval_seconds: float = 30.0
    dedupe_by_bucket: bool = True


class SignalAlertNotifier:
    """Dedupe/throttle wrapper around Discord/Telegram trade-signal alerts."""

    def __init__(
        self,
        config: SignalAlertConfig,
        *,
        sender: Optional[Callable[[str, str], None]] = None,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.config = config
        self._sender = sender
        self._time_fn = time_fn or time.time
        self._last_sent_at: float = 0.0
        self._last_signature: Optional[tuple] = None

    def is_enabled(self) -> bool:
        if not self.config.enabled:
            return False
        provider = self.config.provider.strip().lower()
        if provider == "discord":
            return bool(self.config.discord_webhook_url.strip())
        if provider == "telegram":
            return bool(self.config.telegram_bot_token.strip() and self.config.telegram_chat_id.strip())
        return False

    def _signature(self, signal: TradeSignal) -> tuple:
        try:
            ts_epoch = _parse_iso_to_epoch(signal.timestamp)
            bucket = _bucket_5m(ts_epoch)
        except Exception:
            bucket = None
        if self.config.dedupe_by_bucket:
            return (bucket, signal.direction)
        return (signal.timestamp, signal.direction, round(signal.suggested_size_usdc, 2))

    def _send(self, provider: str, message: str) -> None:
        if self._sender is not None:
            self._sender(provider, message)
            return
        if provider == "discord":
            send_discord_webhook(self.config.discord_webhook_url, message)
            return
        if provider == "telegram":
            send_telegram_message(
                self.config.telegram_bot_token,
                self.config.telegram_chat_id,
                message,
            )
            return
        raise ValueError(f"unsupported alert provider: {provider}")

    def notify(self, signal: TradeSignal) -> tuple[bool, str]:
        """Attempt alert send. Returns (sent, reason)."""
        if not self.is_enabled():
            return False, "disabled"
        if self.config.actionable_only and not is_actionable_trade_signal(signal):
            return False, "not_actionable"

        now = float(self._time_fn())
        min_interval = max(0.0, float(self.config.min_interval_seconds))
        if min_interval > 0 and (now - self._last_sent_at) < min_interval:
            return False, "throttled"

        sig = self._signature(signal)
        if self.config.dedupe_by_bucket and sig == self._last_signature:
            return False, "duplicate_bucket"

        provider = self.config.provider.strip().lower()
        msg = format_trade_signal_alert(signal)
        self._send(provider, msg)
        self._last_sent_at = now
        self._last_signature = sig
        return True, "sent"

