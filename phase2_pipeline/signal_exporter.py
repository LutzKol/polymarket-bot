#!/usr/bin/env python3
"""Offline signal exporter: feature CSV -> EV-engine trade signals CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional

from phase2_pipeline.ev_engine import EVCalculator, KellySizer, ModelLoader, RiskManager, evaluate_signal
from phase2_pipeline.feature_extractor import FEATURE_COLUMNS
from phase2_pipeline.feature_normalizer import FeatureNormalizer
from phase2_pipeline.trade_signal import TradeSignal


def _to_float(value: object, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    s = str(value).strip()
    if s == "":
        return default
    return float(s)


def _read_feature_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _feature_values_from_row(row: dict, feature_columns: list[str]) -> dict:
    out: dict[str, Optional[float]] = {}
    for col in feature_columns:
        out[col] = _to_float(row.get(col), None)
    return out


def _market_prob_from_row(row: dict) -> float:
    pm_mid = _to_float(row.get("pm_mid_prob"), None)
    if pm_mid is None:
        return 0.5
    return max(0.001, min(0.999, float(pm_mid)))


def export_signals_from_feature_csv(
    *,
    input_csv: Path,
    output_csv: Path,
    model_path: str,
    model_feature_columns: Optional[list[str]] = None,
    bankroll_usdc: float = 1000.0,
    max_fraction_per_trade: float = 0.02,
    ev_threshold: float = 0.02,
    brier_gate: float = 0.24,
    max_consecutive_losses: int = 3,
    skip_invalid_rows: bool = True,
) -> dict:
    """Generate trade_signals.csv from feature CSV rows using the EV engine."""
    if not input_csv.exists():
        raise FileNotFoundError(f"feature CSV not found: {input_csv}")
    if not model_path:
        raise ValueError("model_path is required")

    feature_cols = list(model_feature_columns or FEATURE_COLUMNS)
    model = ModelLoader(model_path, feature_columns=feature_cols)
    risk_manager = RiskManager(
        max_consecutive_losses=max_consecutive_losses,
        brier_gate=brier_gate,
        max_fraction=max_fraction_per_trade,
    )
    ev_calc = EVCalculator(ev_threshold=ev_threshold)
    kelly = KellySizer(max_fraction=max_fraction_per_trade)
    normalizer = FeatureNormalizer()

    rows = _read_feature_rows(input_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    rows_total = 0
    rows_invalid = 0
    rows_model_none = 0

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TradeSignal.csv_columns())
        writer.writeheader()

        for row in rows:
            rows_total += 1
            ts = (row.get("timestamp_utc") or "").strip()
            if not ts:
                rows_invalid += 1
                if skip_invalid_rows:
                    continue

            try:
                features_raw = _feature_values_from_row(row, feature_cols)
                normalizer.update(features_raw)
                features_norm = normalizer.normalize(features_raw)
                market_prob = _market_prob_from_row(row)

                signal = evaluate_signal(
                    features=features_norm,
                    model=model,
                    market_prob=market_prob,
                    bankroll=bankroll_usdc,
                    risk_manager=risk_manager,
                    ev_calculator=ev_calc,
                    kelly_sizer=kelly,
                    oracle_stale=False,
                )
                if ts:
                    signal.timestamp = ts
            except Exception:
                rows_invalid += 1
                if skip_invalid_rows:
                    continue
                raise

            if "model_output_none" in (signal.reason or ""):
                rows_model_none += 1

            writer.writerow(signal.to_dict())
            rows_written += 1

    return {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "model_path": model_path,
        "feature_columns": feature_cols,
        "rows_total": rows_total,
        "rows_written": rows_written,
        "rows_invalid": rows_invalid,
        "rows_model_none": rows_model_none,
    }


def _load_config(path: Optional[str]) -> dict:
    if not path:
        return {}
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"config file not found: {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate trade_signals.csv from exported feature CSV using EV engine."
    )
    parser.add_argument("--input-csv", required=True, help="Feature CSV (phase3_features_*.csv)")
    parser.add_argument("--output-csv", default="data/trade_signals.csv", help="Signals CSV output")
    parser.add_argument("--config", default=None, help="Optional config.json path for defaults")
    parser.add_argument("--model-path", default=None, help="Model file path (.json/.pkl/.joblib)")
    parser.add_argument("--starting-bankroll", type=float, default=None, help="Override bankroll_usdc")
    parser.add_argument("--max-fraction-per-trade", type=float, default=None)
    parser.add_argument("--ev-threshold", type=float, default=None)
    parser.add_argument("--brier-gate", type=float, default=None)
    parser.add_argument("--max-consecutive-losses", type=int, default=None)
    parser.add_argument(
        "--model-feature-columns",
        nargs="+",
        default=None,
        help="Override model feature columns (default: config or full FEATURE_COLUMNS)",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)
    model_path = args.model_path or cfg.get("model_path", "")
    bankroll_usdc = (
        args.starting_bankroll if args.starting_bankroll is not None else float(cfg.get("bankroll_usdc", 1000.0))
    )
    max_fraction = (
        args.max_fraction_per_trade
        if args.max_fraction_per_trade is not None
        else float(cfg.get("max_fraction_per_trade", 0.02))
    )
    ev_threshold = (
        args.ev_threshold if args.ev_threshold is not None else float(cfg.get("ev_threshold", 0.02))
    )
    brier_gate = args.brier_gate if args.brier_gate is not None else float(cfg.get("brier_gate", 0.24))
    max_losses = (
        args.max_consecutive_losses
        if args.max_consecutive_losses is not None
        else int(cfg.get("max_consecutive_losses", 3))
    )
    feature_cols = args.model_feature_columns or cfg.get("model_feature_columns") or FEATURE_COLUMNS

    report = export_signals_from_feature_csv(
        input_csv=Path(args.input_csv),
        output_csv=Path(args.output_csv),
        model_path=str(model_path),
        model_feature_columns=[str(c) for c in feature_cols],
        bankroll_usdc=bankroll_usdc,
        max_fraction_per_trade=max_fraction,
        ev_threshold=ev_threshold,
        brier_gate=brier_gate,
        max_consecutive_losses=max_losses,
    )

    print("=== Signal Export Report ===")
    print(f"Input:        {report['input_csv']}")
    print(f"Output:       {report['output_csv']}")
    print(f"Model:        {report['model_path']}")
    print(f"Rows total:   {report['rows_total']}")
    print(f"Rows written: {report['rows_written']}")
    print(f"Rows invalid: {report['rows_invalid']}")
    print(f"Rows model_none: {report['rows_model_none']}")


if __name__ == "__main__":
    main()

