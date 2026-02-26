"""Polymarket CLOB client utilities (REST polling + dynamic token rotation)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
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


def _decode_json_listish(value) -> list:
    """Decode JSON list stored as string, or return list unchanged."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return decoded
        except Exception:
            return []
    return []


def _normalize_outcome_label(value) -> str:
    return str(value).strip().lower()


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


def fetch_json(url: str, *, params: Optional[dict] = None, timeout_seconds: float = 10.0) -> object:
    """Fetch arbitrary JSON with urllib to keep dependencies minimal."""
    full_url = url
    if params:
        full_url = f"{url}?{urlencode(params)}"
    req = Request(full_url, headers={"User-Agent": "polymarketbot-phase2/1.0"})
    with urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def next_5m_boundary_timestamps(count: int = 6, now: Optional[datetime] = None) -> list[int]:
    """Return upcoming 5-minute UTC boundary timestamps."""
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)

    minutes = now.minute
    next_5min = (minutes // 5 + 1) * 5
    if next_5min >= 60:
        boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        boundary = now.replace(minute=next_5min, second=0, microsecond=0)

    result: list[int] = []
    for _ in range(max(1, int(count))):
        result.append(int(boundary.timestamp()))
        boundary += timedelta(minutes=5)
    return result


def extract_btc_5m_market_candidates_from_event_detail(full_event: dict) -> list[dict]:
    """Extract candidate BTC 5m markets from a Gamma event detail payload."""
    markets = full_event.get("markets", [])
    out: list[dict] = []
    if not isinstance(markets, list):
        return out

    for market in markets:
        if not isinstance(market, dict):
            continue
        token_ids = _decode_json_listish(market.get("clobTokenIds"))
        outcomes = _decode_json_listish(market.get("outcomes"))
        if len(token_ids) < 2:
            continue
        if len(outcomes) < 2:
            outcomes = ["Up", "Down"]
        out.append(
            {
                "token_ids": [str(x) for x in token_ids],
                "outcomes": [str(x) for x in outcomes],
            }
        )
    return out


def select_yes_token_id_from_market(market: dict) -> Optional[str]:
    """Pick the YES token id for BTC Up/Down market (prefer 'Up')."""
    token_ids = market.get("token_ids", [])
    outcomes = market.get("outcomes", [])
    if not isinstance(token_ids, list) or len(token_ids) < 2:
        return None
    if not isinstance(outcomes, list) or len(outcomes) < 2:
        return str(token_ids[0])

    normalized = [_normalize_outcome_label(x) for x in outcomes]
    for preferred in ("up", "yes"):
        if preferred in normalized:
            idx = normalized.index(preferred)
            if idx < len(token_ids):
                return str(token_ids[idx])
    return str(token_ids[0])


def resolve_btc_5m_yes_token(
    gamma_base_url: str = "https://gamma-api.polymarket.com",
    *,
    search_count: int = 6,
    timeout_seconds: float = 10.0,
) -> Optional[dict]:
    """Resolve current/next BTC 5m market YES token via Gamma API.

    Returns a dict with keys: slug, timestamp, token_id, outcomes, token_ids.
    """
    for ts in next_5m_boundary_timestamps(search_count):
        slug = f"btc-updown-5m-{ts}"
        events = fetch_json(
            f"{gamma_base_url.rstrip('/')}/events",
            params={"slug": slug},
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(events, list):
            continue

        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = event.get("id")
            if event_id is None:
                continue
            detail = fetch_json(
                f"{gamma_base_url.rstrip('/')}/events/{event_id}",
                timeout_seconds=timeout_seconds,
            )
            if not isinstance(detail, dict):
                continue

            candidates = extract_btc_5m_market_candidates_from_event_detail(detail)
            for market in candidates:
                token_id = select_yes_token_id_from_market(market)
                if token_id:
                    return {
                        "slug": slug,
                        "timestamp": ts,
                        "token_id": token_id,
                        "token_ids": market.get("token_ids", []),
                        "outcomes": market.get("outcomes", []),
                    }
    return None


def fetch_market_resolution(
    slug: str,
    gamma_base_url: str = "https://gamma-api.polymarket.com",
    timeout_seconds: float = 5.0,
) -> Optional[dict]:
    """Check if a BTC 5m market has resolved via Gamma API.

    Returns dict with keys: resolved, outcome_up, outcome_prices, closed_time.
    Returns None if event/market not found.
    """
    try:
        events = fetch_json(
            f"{gamma_base_url.rstrip('/')}/events",
            params={"slug": slug},
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        return None

    if not isinstance(events, list) or len(events) == 0:
        return None

    event = events[0]
    if not isinstance(event, dict):
        return None

    markets = event.get("markets", [])
    if not isinstance(markets, list) or len(markets) == 0:
        return None

    market = markets[0]
    if not isinstance(market, dict):
        return None

    closed = market.get("closed", False)
    if not closed:
        return {"resolved": False, "outcome_up": None, "outcome_prices": [], "closed_time": None}

    outcome_prices = _decode_json_listish(market.get("outcomePrices", []))
    closed_time = market.get("endDate") or market.get("closedTime") or ""

    # Determine outcome: outcomePrices = ["1","0"] means first outcome won.
    # For BTC up/down markets, outcomes[0] is typically "Up".
    outcome_up: Optional[bool] = None
    if len(outcome_prices) >= 2:
        try:
            p0 = float(outcome_prices[0])
            p1 = float(outcome_prices[1])
            if p0 == 1.0 and p1 == 0.0:
                outcome_up = True  # "Up" won
            elif p0 == 0.0 and p1 == 1.0:
                outcome_up = False  # "Down" won
            # else: unclear resolution, leave as None
        except (TypeError, ValueError):
            pass

    if outcome_up is None:
        # Closed but no clear binary outcome
        return {"resolved": False, "outcome_up": None, "outcome_prices": outcome_prices, "closed_time": closed_time}

    return {
        "resolved": True,
        "outcome_up": outcome_up,
        "outcome_prices": outcome_prices,
        "closed_time": closed_time,
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


class RotatingPolymarketBookPoller:
    """Poll /book and auto-rotate token_id by discovering upcoming BTC 5m markets."""

    def __init__(
        self,
        *,
        base_url: str = "https://clob.polymarket.com",
        gamma_base_url: str = "https://gamma-api.polymarket.com",
        poll_seconds: float = 1.0,
        rotate_check_seconds: float = 15.0,
        timeout_seconds: float = 10.0,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.base_url = base_url
        self.gamma_base_url = gamma_base_url
        self.poll_seconds = poll_seconds
        self.rotate_check_seconds = rotate_check_seconds
        self.timeout_seconds = timeout_seconds
        self.logger = logger or print
        self._current_token_id: Optional[str] = None
        self._current_slug: Optional[str] = None
        self._current_event_ts: Optional[int] = None
        self._last_resolve_attempt_monotonic: float = 0.0

    def _should_resolve(self, now_mono: float) -> bool:
        if self._current_token_id is None:
            return True
        if (now_mono - self._last_resolve_attempt_monotonic) >= self.rotate_check_seconds:
            return True
        if self._current_event_ts is None:
            return False
        # Rotate shortly after the market boundary has passed.
        return datetime.now(timezone.utc).timestamp() >= (self._current_event_ts + 2)

    async def _resolve_token(self) -> None:
        self._last_resolve_attempt_monotonic = asyncio.get_running_loop().time()
        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(
                    resolve_btc_5m_yes_token,
                    self.gamma_base_url,
                    search_count=8,
                    timeout_seconds=self.timeout_seconds,
                ),
                timeout=self.timeout_seconds + 4.0,
            )
        except asyncio.TimeoutError:
            self.logger("[PM] timeout while resolving dynamic BTC 5m token via Gamma")
            return
        except (HTTPError, URLError) as exc:
            self.logger(f"[PM] gamma http/network error: {exc}")
            return
        except Exception as exc:
            self.logger(f"[PM] gamma resolve error: {exc}")
            return

        if not info:
            self.logger("[PM] no BTC 5m token found via Gamma")
            return

        token_id = str(info["token_id"])
        slug = str(info.get("slug", ""))
        ts = int(info.get("timestamp", 0)) if info.get("timestamp") is not None else None
        if token_id != self._current_token_id:
            self._current_token_id = token_id
            self._current_slug = slug
            self._current_event_ts = ts
            self.logger(
                f"[PM] rotated token -> slug={slug} token_id={token_id}"
            )
        else:
            self._current_slug = slug
            self._current_event_ts = ts

    async def run(self, stop_event: asyncio.Event, on_book: Callable[[dict], None]) -> None:
        while not stop_event.is_set():
            now_mono = asyncio.get_running_loop().time()
            if self._should_resolve(now_mono):
                await self._resolve_token()

            if self._current_token_id:
                try:
                    book = await asyncio.wait_for(
                        asyncio.to_thread(
                            fetch_polymarket_book,
                            self.base_url,
                            self._current_token_id,
                            self.timeout_seconds,
                        ),
                        timeout=self.timeout_seconds + 2.0,
                    )
                    # Attach resolver metadata for logging/inspection if needed.
                    if isinstance(book, dict):
                        book = dict(book)
                        book["_pm_token_id"] = self._current_token_id
                        if self._current_slug is not None:
                            book["_pm_slug"] = self._current_slug
                    on_book(book)
                except asyncio.TimeoutError:
                    self.logger("[PM] timeout while fetching /book (rotating poller)")
                except (HTTPError, URLError) as exc:
                    self.logger(f"[PM] http/network error (rotating poller): {exc}")
                except Exception as exc:
                    self.logger(f"[PM] unexpected error (rotating poller): {exc}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass
