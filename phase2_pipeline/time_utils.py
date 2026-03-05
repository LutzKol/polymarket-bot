"""Time helpers for market-round features."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def seconds_remaining_in_5m_window(now: Optional[datetime] = None) -> float:
    """Seconds remaining in current 5-minute bucket.

    Returns values in (0, 300], where 300 means bucket boundary.
    """
    ts = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    epoch = int(ts.timestamp())
    mod = epoch % 300
    return 300.0 if mod == 0 else float(300 - mod)

