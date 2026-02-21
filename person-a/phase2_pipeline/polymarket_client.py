"""Polymarket CLOB client utilities (REST polling variant)."""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _as_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_price(value: Optional[float]) -> Optional[float]:
    """Normalize price to probability-like [0,1] when possible."""
    if value is None:
        return None
    if 0.0 <= value <= 1.0:
        return value
    if 1.0 < value <= 100.0:
        return value / 100.0
    return None


def _extract_levels(raw_levels) -> list[list[float]]:
    levels: list[list[float]] = []
    if not isinstance(raw_levels, list):
        return levels

    for level in raw_levels:
        price = None
        size = None

        if isinstance(level, (list, tuple)):
            if len(level) >= 2:
                price = _as_float(level[0])
                size = _as_float(level[1])
        elif isinstance(level, dict):
            price = _as_float(level.get("price"))
            if price is None:
                price = _as_float(level.get("p"))
            size = _as_float(level.get("size"))
            if size is None:
                size = _as_float(level.get("s"))
            if size is None:
                size = _as_float(level.get("quantity"))

        if price is None or size is None or size < 0:
            continue
        levels.append([price, size])

    return levels


def parse_polymarket_book(payload: dict) -> dict:
    """Parse CLOB book payload into a normalized structure."""
    bids = _extract_levels(payload.get("bids", payload.get("b", [])))
    asks = _extract_levels(payload.get("asks", payload.get("a", [])))

    best_bid_raw = _as_float(payload.get("best_bid"))
    if best_bid_raw is None and bids:
        best_bid_raw = bids[0][0]

    best_ask_raw = _as_float(payload.get("best_ask"))
    if best_ask_raw is None and asks:
        best_ask_raw = asks[0][0]

    best_bid = _normalize_price(best_bid_raw)
    best_ask = _normalize_price(best_ask_raw)

    implied_mid_prob = None
    spread = None
    if best_bid is not None and best_ask is not None:
        implied_mid_prob = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

    return {
        "bids": bids,
        "asks": asks,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "implied_mid_prob": implied_mid_prob,
        "spread": spread,
    }


def fetch_polymarket_book(base_url: str, token_id: str, timeout_seconds: float = 10.0) -> dict:
    query = urlencode({"token_id": token_id})
    url = f"{base_url.rstrip('/')}/book?{query}"
    req = Request(url, headers={"User-Agent": "polymarketbot-phase2/1.0"})
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected book payload: expected JSON object")
    return parse_polymarket_book(payload)


class PolymarketBookPoller:
    """Async wrapper around periodic REST book fetches."""

    def __init__(
        self,
        *,
        token_id: str,
        base_url: str = "https://clob.polymarket.com",
        poll_seconds: float = 1.0,
        timeout_seconds: float = 10.0,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.token_id = token_id
        self.base_url = base_url
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.logger = logger or print

    async def run(self, stop_event: asyncio.Event, on_book: Callable[[dict], None]) -> None:
        while not stop_event.is_set():
            try:
                book = await asyncio.wait_for(
                    asyncio.to_thread(
                        fetch_polymarket_book,
                        self.base_url,
                        self.token_id,
                        self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds + 2.0,
                )
                on_book(book)
            except asyncio.TimeoutError:
                self.logger("[PM] timeout while fetching /book")
            except (HTTPError, URLError) as exc:
                self.logger(f"[PM] http/network error: {exc}")
            except Exception as exc:
                self.logger(f"[PM] unexpected error: {exc}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

