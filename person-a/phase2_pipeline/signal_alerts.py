"""Trade-signal alerts (Discord/Telegram) for actionable EV proposals."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.request import Request, urlopen

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

