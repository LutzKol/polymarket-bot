"""Feature extraction for Phase 3 handoff datasets."""

from __future__ import annotations

import math
from typing import Optional

from phase2_pipeline.features import calculate_obi, log_return


FEATURE_COLUMNS = [
    "oracle_lag_pct",
    "momentum_30s",
    "momentum_60s",
    "slope",
    "sigma_short",
    "sigma_long",
    "sigma_ratio",
    "obi",
    "cvd_60s",
    "tau",
    "tau_sq",
    "funding_rate",
    "pm_best_bid",
    "pm_best_ask",
    "pm_mid_prob",
    "pm_spread",
    "pm_obi",
]


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_ewma_sigma(prices: list[float], lam: float) -> Optional[float]:
    if len(prices) < 2:
        return None

    returns: list[float] = []
    for idx in range(1, len(prices)):
        r = log_return(prices[idx], prices[idx - 1])
        if r is not None:
            returns.append(r)

    if not returns:
        return None

    var = returns[0] * returns[0]
    for r in returns[1:]:
        var = lam * var + (1.0 - lam) * (r * r)

    return math.sqrt(var)


def _calc_slope(values: list[float], window: int = 10) -> Optional[float]:
    if len(values) < window:
        return None
    y = values[-window:]
    x = list(range(window))
    x_mean = sum(x) / window
    y_mean = sum(y) / window

    num = 0.0
    den = 0.0
    for xi, yi in zip(x, y):
        dx = xi - x_mean
        num += dx * (yi - y_mean)
        den += dx * dx

    if den == 0:
        return None
    return num / den


class FeatureExtractor:
    """Extract normalized feature dict from a unified state snapshot."""

    def extract(self, snapshot: dict) -> dict:
        oracle_prices = [_safe_float(x) for x in snapshot.get("oracle_prices", [])]
        spot_prices = [_safe_float(x) for x in snapshot.get("spot_prices", [])]
        oracle_prices = [x for x in oracle_prices if x is not None]
        spot_prices = [x for x in spot_prices if x is not None]

        oracle_last = oracle_prices[-1] if oracle_prices else None
        spot_last = spot_prices[-1] if spot_prices else None

        oracle_lag_pct = None
        if oracle_last and spot_last and oracle_last != 0:
            oracle_lag_pct = ((spot_last - oracle_last) / oracle_last) * 100.0

        momentum_30s = None
        if len(spot_prices) >= 31:
            momentum_30s = log_return(spot_prices[-1], spot_prices[-31])

        momentum_60s = None
        if len(spot_prices) >= 61:
            momentum_60s = log_return(spot_prices[-1], spot_prices[-61])

        slope = _calc_slope(oracle_prices, window=10)
        sigma_short = _calc_ewma_sigma(spot_prices, lam=0.94)
        sigma_long = _calc_ewma_sigma(spot_prices, lam=0.97)

        sigma_ratio = None
        if sigma_short is not None and sigma_long not in (None, 0.0):
            sigma_ratio = sigma_short / sigma_long

        pm_orderbook = snapshot.get("polymarket_orderbook", {})
        binance_orderbook = snapshot.get("orderbook", {})
        pm_obi = calculate_obi(pm_orderbook)
        obi = pm_obi if pm_obi is not None else calculate_obi(binance_orderbook)
        cvd_60s = _safe_float(snapshot.get("cvd_60s"))
        funding_rate = _safe_float(snapshot.get("funding_rate"))
        pm_best_bid = _safe_float(snapshot.get("pm_best_bid"))
        pm_best_ask = _safe_float(snapshot.get("pm_best_ask"))
        pm_mid_prob = _safe_float(snapshot.get("pm_mid_prob"))
        pm_spread = _safe_float(snapshot.get("pm_spread"))

        seconds_remaining = _safe_float(snapshot.get("seconds_remaining"))
        tau = None
        tau_sq = None
        if seconds_remaining is not None:
            tau = seconds_remaining / 300.0
            tau_sq = tau * tau

        out = {
            "oracle_lag_pct": oracle_lag_pct,
            "momentum_30s": momentum_30s,
            "momentum_60s": momentum_60s,
            "slope": slope,
            "sigma_short": sigma_short,
            "sigma_long": sigma_long,
            "sigma_ratio": sigma_ratio,
            "obi": obi,
            "cvd_60s": cvd_60s,
            "tau": tau,
            "tau_sq": tau_sq,
            "funding_rate": funding_rate,
            "pm_best_bid": pm_best_bid,
            "pm_best_ask": pm_best_ask,
            "pm_mid_prob": pm_mid_prob,
            "pm_spread": pm_spread,
            "pm_obi": pm_obi,
        }
        return out
