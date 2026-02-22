"""Config validation and coercion for Phase 2 pipeline."""

from __future__ import annotations

REQUIRED_KEYS = ["polygon_rpc_url"]

DEFAULTS = {
    "chainlink_address": "0xc907E116054Ad103354f2D350FD2514433D57F6f",
    "oracle_poll_seconds": 5.0,
    "alert_threshold_pct": 0.35,
    "polymarket_base_url": "https://clob.polymarket.com",
    "polymarket_token_id": "",
    "polymarket_poll_seconds": 1.0,
    "funding_enabled": True,
    "funding_symbol": "BTCUSDT",
    "funding_base_url": "https://fapi.binance.com",
    "funding_poll_seconds": 30.0,
    "log_file": "oracle_lag_log.csv",
    "max_oracle_age_seconds": 300.0,
    # Phase 4: EV-Engine
    "model_path": "",
    "model_feature_columns": ["oracle_lag_pct", "sigma_short", "momentum_30s"],
    "bankroll_usdc": 1000.0,
    "max_fraction_per_trade": 0.02,
    "ev_threshold": 0.02,
    "brier_gate": 0.24,
    "max_consecutive_losses": 3,
    "signal_csv_path": "data/trade_signals.csv",
}

FLOAT_FIELDS = {
    "oracle_poll_seconds",
    "alert_threshold_pct",
    "polymarket_poll_seconds",
    "funding_poll_seconds",
    "max_oracle_age_seconds",
    "bankroll_usdc",
    "max_fraction_per_trade",
    "ev_threshold",
    "brier_gate",
}

POSITIVE_FLOAT_FIELDS = {
    "oracle_poll_seconds",
    "alert_threshold_pct",
    "polymarket_poll_seconds",
    "funding_poll_seconds",
    "max_oracle_age_seconds",
    "bankroll_usdc",
    "max_fraction_per_trade",
    "ev_threshold",
}


def validate_config(config: dict) -> dict:
    """Validate, coerce types, and apply defaults to a config dict.

    Returns a new dict with validated values.
    Raises ValueError for missing required keys or invalid values.
    """
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")

    for key in REQUIRED_KEYS:
        if key not in config or not config[key]:
            raise ValueError(f"missing required config key: {key}")

    result = dict(config)

    for key, default in DEFAULTS.items():
        if key not in result:
            result[key] = default

    for key in FLOAT_FIELDS:
        if key in result:
            try:
                result[key] = float(result[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"config key {key!r} must be numeric, got {result[key]!r}") from exc

    for key in POSITIVE_FLOAT_FIELDS:
        if key in result and result[key] <= 0:
            raise ValueError(f"config key {key!r} must be > 0, got {result[key]}")

    return result
