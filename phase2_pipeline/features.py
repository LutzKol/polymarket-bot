"""Feature helpers for Phase 2/3.

This module focuses on deterministic, testable calculations.
"""

from __future__ import annotations

import math
from typing import Iterable, Optional


def _to_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_obi(orderbook: dict, levels: int = 5) -> Optional[float]:
    """Calculate weighted orderbook imbalance.

    Expected orderbook shape:
    {
        "bids": [[price, qty], ...],
        "asks": [[price, qty], ...],
    }

    Returns:
        float in [-1, 1], or None when there is insufficient/invalid data.
    """
    if not isinstance(orderbook, dict):
        return None

    bids = orderbook.get("bids")
    asks = orderbook.get("asks")
    if not isinstance(bids, list) or not isinstance(asks, list):
        return None
    if len(bids) < levels or len(asks) < levels:
        return None

    bid_weighted = 0.0
    ask_weighted = 0.0

    for idx in range(levels):
        bid_level = bids[idx]
        ask_level = asks[idx]
        if not isinstance(bid_level, (list, tuple)) or not isinstance(ask_level, (list, tuple)):
            return None
        if len(bid_level) < 2 or len(ask_level) < 2:
            return None

        bid_qty = _to_float(bid_level[1])
        ask_qty = _to_float(ask_level[1])
        if bid_qty is None or ask_qty is None:
            return None
        if bid_qty < 0 or ask_qty < 0:
            return None

        weight = 1.0 / (idx + 1)
        bid_weighted += bid_qty * weight
        ask_weighted += ask_qty * weight

    denominator = bid_weighted + ask_weighted
    if denominator <= 0:
        return None

    obi = (bid_weighted - ask_weighted) / denominator
    return max(-1.0, min(1.0, obi))


def update_cvd(current_cvd: float, side: str, qty: float) -> float:
    """Update cumulative volume delta using one trade event."""
    side_normalized = (side or "").strip().lower()
    qty_value = _to_float(qty)
    if qty_value is None or qty_value < 0:
        raise ValueError("qty must be a non-negative number")

    if side_normalized in {"buy", "bid", "b"}:
        return current_cvd + qty_value
    if side_normalized in {"sell", "ask", "s"}:
        return current_cvd - qty_value
    raise ValueError(f"unsupported side: {side!r}")


def calculate_cvd(trades: Iterable[dict]) -> float:
    """Calculate cumulative volume delta from an iterable of trades."""
    cvd = 0.0
    for trade in trades:
        side = trade.get("side")
        qty = trade.get("qty")
        cvd = update_cvd(cvd, side, qty)
    return cvd


def log_return(current_price: float, reference_price: float) -> Optional[float]:
    """Safe log-return helper used in momentum features."""
    current = _to_float(current_price)
    reference = _to_float(reference_price)
    if current is None or reference is None:
        return None
    if current <= 0 or reference <= 0:
        return None
    return math.log(current / reference)

