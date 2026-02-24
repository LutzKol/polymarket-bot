"""In-memory unified state for Phase 2 multi-feed pipeline."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from phase2_pipeline.features import update_cvd


def _utc_now() -> datetime:
    return datetime.utcnow()


@dataclass
class TradeTick:
    ts: datetime
    side: str
    qty: float


class UnifiedStateStore:
    """Single source of truth for synchronized feed state."""

    def __init__(self, history_size: int = 900):
        if history_size < 60:
            raise ValueError("history_size should be >= 60")

        self.history_size = history_size
        self.oracle_prices: deque[float] = deque(maxlen=history_size)
        self.spot_prices: deque[float] = deque(maxlen=history_size)
        self.oracle_round_ids: deque[int] = deque(maxlen=history_size)
        self.oracle_updated_at: Optional[int] = None
        self.orderbook: dict = {"bids": [], "asks": []}
        self.polymarket_orderbook: dict = {"bids": [], "asks": []}
        self.pm_best_bid: Optional[float] = None
        self.pm_best_ask: Optional[float] = None
        self.pm_mid_prob: Optional[float] = None
        self.pm_spread: Optional[float] = None
        self.funding_rate: Optional[float] = None
        self.seconds_remaining: Optional[float] = None
        self.trades: deque[TradeTick] = deque(maxlen=history_size * 20)
        self.cvd_total: float = 0.0

    def update_oracle(self, price: float, round_id: int, updated_at: int) -> None:
        self.oracle_prices.append(float(price))
        self.oracle_round_ids.append(int(round_id))
        self.oracle_updated_at = int(updated_at)

    def update_spot(self, price: float) -> None:
        self.spot_prices.append(float(price))

    def update_orderbook(self, bids: list, asks: list) -> None:
        self.orderbook = {
            "bids": list(bids),
            "asks": list(asks),
        }

    def update_polymarket_orderbook(
        self,
        *,
        bids: list,
        asks: list,
        best_bid: Optional[float],
        best_ask: Optional[float],
        mid_prob: Optional[float],
        spread: Optional[float],
    ) -> None:
        self.polymarket_orderbook = {
            "bids": list(bids),
            "asks": list(asks),
        }
        self.pm_best_bid = None if best_bid is None else float(best_bid)
        self.pm_best_ask = None if best_ask is None else float(best_ask)
        self.pm_mid_prob = None if mid_prob is None else float(mid_prob)
        self.pm_spread = None if spread is None else float(spread)

    def update_funding_rate(self, funding_rate: float) -> None:
        self.funding_rate = float(funding_rate)

    def update_seconds_remaining(self, seconds_remaining: float) -> None:
        self.seconds_remaining = float(seconds_remaining)

    def add_trade(self, side: str, qty: float, ts: Optional[datetime] = None) -> None:
        ts_value = ts or _utc_now()
        qty_value = float(qty)
        self.cvd_total = update_cvd(self.cvd_total, side, qty_value)
        self.trades.append(TradeTick(ts=ts_value, side=side, qty=qty_value))
        self._prune_old_trades()

    def cvd_window(self, window_seconds: int = 60, now: Optional[datetime] = None) -> float:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")

        now_ts = now or _utc_now()
        cutoff = now_ts - timedelta(seconds=window_seconds)
        cvd = 0.0
        for trade in self.trades:
            if trade.ts < cutoff:
                continue
            cvd = update_cvd(cvd, trade.side, trade.qty)
        return cvd

    def snapshot(self, seconds_remaining: Optional[float] = None) -> dict:
        secs = self.seconds_remaining if seconds_remaining is None else seconds_remaining
        return {
            "oracle_prices": list(self.oracle_prices),
            "spot_prices": list(self.spot_prices),
            "orderbook": self.orderbook,
            "polymarket_orderbook": self.polymarket_orderbook,
            "pm_best_bid": self.pm_best_bid,
            "pm_best_ask": self.pm_best_ask,
            "pm_mid_prob": self.pm_mid_prob,
            "pm_spread": self.pm_spread,
            "cvd_60s": self.cvd_window(60),
            "seconds_remaining": secs,
            "funding_rate": self.funding_rate,
            "oracle_updated_at": self.oracle_updated_at,
            "oracle_round_ids": list(self.oracle_round_ids),
        }

    def _prune_old_trades(self) -> None:
        if not self.trades:
            return
        newest_ts = self.trades[-1].ts
        cutoff = newest_ts - timedelta(minutes=15)
        while self.trades and self.trades[0].ts < cutoff:
            self.trades.popleft()
