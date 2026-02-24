"""Binance funding-rate polling utilities."""

from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def parse_binance_premium_index(payload: dict) -> float:
    """Extract last funding rate from /fapi/v1/premiumIndex payload."""
    raw = payload.get("lastFundingRate")
    if raw is None:
        raise ValueError("missing lastFundingRate field")
    return float(raw)


def fetch_binance_funding_rate(
    *,
    symbol: str = "BTCUSDT",
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 10.0,
) -> float:
    query = urlencode({"symbol": symbol})
    url = f"{base_url.rstrip('/')}/fapi/v1/premiumIndex?{query}"
    req = Request(url, headers={"User-Agent": "polymarketbot-phase2/1.0"})
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Unexpected funding payload: expected JSON object")
    return parse_binance_premium_index(payload)


class FundingRatePoller:
    """Async wrapper around periodic funding rate fetches."""

    def __init__(
        self,
        *,
        symbol: str = "BTCUSDT",
        base_url: str = "https://fapi.binance.com",
        poll_seconds: float = 30.0,
        timeout_seconds: float = 10.0,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.symbol = symbol
        self.base_url = base_url
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        self.logger = logger or print

    async def run(self, stop_event: asyncio.Event, on_rate: Callable[[float], None]) -> None:
        while not stop_event.is_set():
            try:
                rate = await asyncio.wait_for(
                    asyncio.to_thread(
                        fetch_binance_funding_rate,
                        symbol=self.symbol,
                        base_url=self.base_url,
                        timeout_seconds=self.timeout_seconds,
                    ),
                    timeout=self.timeout_seconds + 2.0,
                )
                on_rate(rate)
            except asyncio.TimeoutError:
                self.logger("[FUNDING] timeout while fetching premiumIndex")
            except (HTTPError, URLError) as exc:
                self.logger(f"[FUNDING] http/network error: {exc}")
            except Exception as exc:
                self.logger(f"[FUNDING] unexpected error: {exc}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

