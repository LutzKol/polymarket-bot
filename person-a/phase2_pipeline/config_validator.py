"""Config validation and coercion for Phase 2 pipeline."""

from __future__ import annotations

REQUIRED_KEYS = ["polygon_rpc_url"]

DEFAULTS = {
    "chainlink_address": "0xc907E116054Ad103354f2D350FD2514433D57F6f",
    "oracle_poll_seconds": 5.0,
    "alert_threshold_pct": 0.35,
    "polymarket_base_url": "https://clob.polymarket.com",
    "polymarket_gamma_base_url": "https://gamma-api.polymarket.com",
    "polymarket_token_id": "",
    "polymarket_auto_rotate": False,
    "polymarket_poll_seconds": 1.0,
    "polymarket_rotate_check_seconds": 15.0,
    "funding_enabled": True,
    "funding_symbol": "BTCUSDT",
    "funding_base_url": "https://fapi.binance.com",
    "funding_poll_seconds": 30.0,
    "log_file": "oracle_lag_log.csv",
    "max_oracle_age_seconds": 300.0,
    # Phase 4: EV-Engine
    "model_path": "",
    "model_feature_columns": None,  # Read from model file when not specified
    "max_pm_spread": 0.20,  # Skip trades when Polymarket spread exceeds this
    "bankroll_usdc": 1000.0,
    "max_fraction_per_trade": 0.02,
    "ev_threshold": 0.02,
    "brier_gate": 0.24,
    "max_consecutive_losses": 3,
    "signal_csv_path": "data/trade_signals.csv",
    # Trade signal alerts (Discord / Telegram)
    "trade_alerts_enabled": False,
    "trade_alert_provider": "",
    "discord_webhook_url": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "trade_alert_only_actionable": True,
    "trade_alert_min_interval_seconds": 30.0,
    "trade_alert_dedupe_by_bucket": True,
    # Phase 5: Paper Trading
    "paper_trading_enabled": False,
    "paper_trades_csv_path": "data/paper_trades.csv",
    "paper_fill_half_spread_bps": 5.0,
    "paper_fill_slippage_bps": 10.0,
    "paper_fill_latency_bps": 5.0,
    "paper_fill_use_variable_fees": True,
    "paper_max_daily_loss_fraction": 0.08,
    "paper_max_trades_per_day": 20,
    "paper_cooldown_after_consecutive_losses": 3,
    "paper_cooldown_minutes": 30.0,
}

FLOAT_FIELDS = {
    "oracle_poll_seconds",
    "alert_threshold_pct",
    "polymarket_poll_seconds",
    "polymarket_rotate_check_seconds",
    "funding_poll_seconds",
    "max_oracle_age_seconds",
    "bankroll_usdc",
    "max_fraction_per_trade",
    "ev_threshold",
    "brier_gate",
    "max_pm_spread",
    "trade_alert_min_interval_seconds",
    "paper_fill_half_spread_bps",
    "paper_fill_slippage_bps",
    "paper_fill_latency_bps",
    "paper_max_daily_loss_fraction",
    "paper_cooldown_minutes",
}

POSITIVE_FLOAT_FIELDS = {
    "oracle_poll_seconds",
    "alert_threshold_pct",
    "polymarket_poll_seconds",
    "polymarket_rotate_check_seconds",
    "funding_poll_seconds",
    "max_oracle_age_seconds",
    "bankroll_usdc",
    "max_fraction_per_trade",
    "ev_threshold",
    "trade_alert_min_interval_seconds",
}

BOOL_FIELDS = {
    "polymarket_auto_rotate",
    "funding_enabled",
    "trade_alerts_enabled",
    "trade_alert_only_actionable",
    "trade_alert_dedupe_by_bucket",
    "paper_trading_enabled",
    "paper_fill_use_variable_fees",
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

    for key in BOOL_FIELDS:
        if key not in result:
            continue
        value = result[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                result[key] = True
                continue
            if lowered in {"0", "false", "no", "off"}:
                result[key] = False
                continue
        raise ValueError(f"config key {key!r} must be boolean, got {value!r}")

    return result
