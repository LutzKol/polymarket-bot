#!/usr/bin/env python3
"""Phase 5 replay runner: signals CSV + labels CSV -> paper trades + stats."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from phase2_pipeline.paper_trading import (
    FillConfig,
    FillSimulator,
    PaperRiskLimits,
    PaperTrade,
    PaperTradingEngine,
)
from phase2_pipeline.trade_signal import TradeSignal


def _parse_iso_to_epoch(ts: str) -> float:
    value = ts.strip()
    if value.endswith("Z"):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _epoch_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bucket_start(ts_epoch: float, bucket_seconds: int = 300) -> int:
    return int(ts_epoch // bucket_seconds) * bucket_seconds


def _to_float(value: object, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    s = str(value).strip()
    if s == "":
        return default
    return float(s)


def _to_bool(value: object) -> bool:
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y"}


@dataclass
class ReplayStats:
    rows_signals_total: int = 0
    rows_signals_skipped_invalid: int = 0
    rows_signals_skipped_no_label: int = 0
    rows_signals_skipped_duplicate_bucket: int = 0
    rows_signals_skipped_not_tradeable: int = 0
    rows_signals_opened: int = 0
    rows_signals_skipped_cooldown: int = 0
    rows_signals_skipped_daily_loss_stop: int = 0
    rows_signals_skipped_max_trades_per_day: int = 0

    def to_dict(self) -> dict:
        return {
            "rows_signals_total": self.rows_signals_total,
            "rows_signals_skipped_invalid": self.rows_signals_skipped_invalid,
            "rows_signals_skipped_no_label": self.rows_signals_skipped_no_label,
            "rows_signals_skipped_duplicate_bucket": self.rows_signals_skipped_duplicate_bucket,
            "rows_signals_skipped_not_tradeable": self.rows_signals_skipped_not_tradeable,
            "rows_signals_opened": self.rows_signals_opened,
            "rows_signals_skipped_cooldown": self.rows_signals_skipped_cooldown,
            "rows_signals_skipped_daily_loss_stop": self.rows_signals_skipped_daily_loss_stop,
            "rows_signals_skipped_max_trades_per_day": self.rows_signals_skipped_max_trades_per_day,
        }


def load_labels_by_bucket(labels_csv: Path) -> dict[int, dict]:
    """Load label rows keyed by bucket_start_ts (int). First row per bucket wins."""
    rows_by_bucket: dict[int, dict] = {}
    with labels_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"bucket_start_ts", "label"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"labels CSV missing required columns {sorted(required)}: {labels_csv}"
            )
        for row in reader:
            key_raw = row.get("bucket_start_ts", "").strip()
            if not key_raw:
                continue
            key = int(float(key_raw))
            rows_by_bucket.setdefault(key, row)
    return rows_by_bucket


def _signal_from_row(row: dict) -> TradeSignal:
    """Parse a TradeSignal from CSV row using TradeSignal.csv_columns schema."""
    return TradeSignal(
        timestamp=row["timestamp"],
        direction=row["direction"],
        model_probability=float(row["model_probability"]),
        market_probability=float(row["market_probability"]),
        ev=float(row["ev"]),
        kelly_fraction=float(row["kelly_fraction"]),
        suggested_size_usdc=float(row["suggested_size_usdc"]),
        risk_checks_passed=_to_bool(row["risk_checks_passed"]),
        reason=row.get("reason", ""),
        bankroll_usdc=float(row["bankroll_usdc"]),
        brier_score=_to_float(row.get("brier_score"), None),
    )


def replay_signals(
    signals_csv: Path,
    labels_csv: Path,
    engine: PaperTradingEngine,
    *,
    one_trade_per_bucket: bool = True,
    min_ev: Optional[float] = None,
) -> tuple[list[PaperTrade], dict]:
    """Replay signals against labeled event outcomes and resolve at bucket end."""
    labels_by_bucket = load_labels_by_bucket(labels_csv)
    stats = ReplayStats()
    used_buckets: set[int] = set()

    with signals_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        required_cols = set(TradeSignal.csv_columns())
        if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"signals CSV missing required columns {sorted(required_cols)}: {signals_csv}"
            )

        for row in reader:
            stats.rows_signals_total += 1

            try:
                signal = _signal_from_row(row)
                ts_epoch = _parse_iso_to_epoch(signal.timestamp)
            except Exception:
                stats.rows_signals_skipped_invalid += 1
                continue

            if min_ev is not None and signal.ev < min_ev:
                stats.rows_signals_skipped_not_tradeable += 1
                continue

            bucket = _bucket_start(ts_epoch)
            if one_trade_per_bucket and bucket in used_buckets:
                stats.rows_signals_skipped_duplicate_bucket += 1
                continue

            label_row = labels_by_bucket.get(bucket)
            if label_row is None:
                stats.rows_signals_skipped_no_label += 1
                continue

            pm_best_bid = _to_float(label_row.get("pm_best_bid"), None)
            pm_best_ask = _to_float(label_row.get("pm_best_ask"), None)
            opened = engine.open_trade(
                signal=signal,
                event_id=f"bucket_{bucket}",
                pm_best_bid=pm_best_bid,
                pm_best_ask=pm_best_ask,
            )
            if opened is None:
                if engine.last_reject_reason == "cooldown_active":
                    stats.rows_signals_skipped_cooldown += 1
                elif engine.last_reject_reason == "daily_loss_stop":
                    stats.rows_signals_skipped_daily_loss_stop += 1
                elif engine.last_reject_reason == "max_trades_per_day":
                    stats.rows_signals_skipped_max_trades_per_day += 1
                stats.rows_signals_skipped_not_tradeable += 1
                continue

            outcome_up = _to_bool(label_row.get("label", "0"))
            engine.resolve_trade(
                opened.trade_id,
                outcome_up=outcome_up,
                closed_at=_epoch_to_iso(bucket + 300),
            )
            used_buckets.add(bucket)
            stats.rows_signals_opened += 1

    return list(engine.closed_trades), stats.to_dict()


def write_trades_csv(trades: list[PaperTrade], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PaperTrade.csv_columns())
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade.to_dict())


def _print_report(summary: dict, replay_stats: dict) -> None:
    print("=== Phase 5 Replay Report ===")
    print(
        "Signals: total={rows_signals_total} opened={rows_signals_opened} "
        "skip_invalid={rows_signals_skipped_invalid} skip_no_label={rows_signals_skipped_no_label} "
        "skip_dup_bucket={rows_signals_skipped_duplicate_bucket} skip_not_tradeable={rows_signals_skipped_not_tradeable} "
        "skip_cooldown={rows_signals_skipped_cooldown} skip_daily={rows_signals_skipped_daily_loss_stop} "
        "skip_max_day={rows_signals_skipped_max_trades_per_day}".format(
            **replay_stats
        )
    )
    print(
        "Trades: closed={closed_trades} wins={wins} losses={losses} win_rate={win_rate:.2%}".format(
            **summary
        )
    )
    print(
        "PnL: total={total_pnl_usdc:.2f} avg={avg_pnl_usdc:.2f} avg_return={avg_return_pct:.2%}".format(
            **summary
        )
    )
    print(
        "Bankroll: start={starting_bankroll_usdc:.2f} end={ending_bankroll_usdc:.2f} mdd={max_drawdown:.2%}".format(
            **summary
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay trade signals against labeled outcomes using paper fill simulation."
    )
    parser.add_argument("--signals-csv", required=True, help="Path to trade_signals.csv")
    parser.add_argument("--labels-csv", required=True, help="Path to labeled_training.csv")
    parser.add_argument(
        "--output-trades-csv",
        default="data/paper_trades.csv",
        help="Output path for simulated trade log CSV",
    )
    parser.add_argument(
        "--output-summary-json",
        default="data/paper_trade_summary.json",
        help="Output path for replay summary JSON",
    )
    parser.add_argument("--starting-bankroll", type=float, default=1000.0)
    parser.add_argument("--min-ev", type=float, default=None)
    parser.add_argument("--allow-multiple-signals-per-bucket", action="store_true")
    parser.add_argument("--half-spread-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--latency-bps", type=float, default=0.0)
    parser.add_argument("--entry-fee-rate", type=float, default=0.0)
    parser.add_argument("--exit-fee-rate", type=float, default=0.0)
    parser.add_argument(
        "--use-variable-fees",
        action="store_true",
        help="Use Polymarket effective fee approximation based on fill price",
    )
    parser.add_argument("--max-daily-loss-fraction", type=float, default=None)
    parser.add_argument("--max-trades-per-day", type=int, default=None)
    parser.add_argument("--cooldown-after-losses", type=int, default=None)
    parser.add_argument("--cooldown-minutes", type=float, default=30.0)
    args = parser.parse_args()

    engine = PaperTradingEngine(
        starting_bankroll_usdc=args.starting_bankroll,
        fill_simulator=FillSimulator(
            FillConfig(
                half_spread_bps=args.half_spread_bps,
                slippage_bps=args.slippage_bps,
                latency_bps=args.latency_bps,
                entry_fee_rate=args.entry_fee_rate,
                exit_fee_rate=args.exit_fee_rate,
                use_variable_fees=bool(args.use_variable_fees),
            )
        ),
        risk_limits=PaperRiskLimits(
            max_daily_loss_fraction=args.max_daily_loss_fraction,
            max_trades_per_day=args.max_trades_per_day,
            cooldown_after_consecutive_losses=args.cooldown_after_losses,
            cooldown_minutes=args.cooldown_minutes,
        ),
    )

    trades, replay_stats = replay_signals(
        signals_csv=Path(args.signals_csv),
        labels_csv=Path(args.labels_csv),
        engine=engine,
        one_trade_per_bucket=not args.allow_multiple_signals_per_bucket,
        min_ev=args.min_ev,
    )
    write_trades_csv(trades, Path(args.output_trades_csv))

    summary = engine.summary()
    payload = {
        "replay_stats": replay_stats,
        "trade_summary": summary,
        "config": {
            "starting_bankroll": args.starting_bankroll,
            "min_ev": args.min_ev,
            "one_trade_per_bucket": not args.allow_multiple_signals_per_bucket,
            "fill": {
                "half_spread_bps": args.half_spread_bps,
                "slippage_bps": args.slippage_bps,
                "latency_bps": args.latency_bps,
                "entry_fee_rate": args.entry_fee_rate,
                "exit_fee_rate": args.exit_fee_rate,
                "use_variable_fees": bool(args.use_variable_fees),
            },
            "risk_limits": {
                "max_daily_loss_fraction": args.max_daily_loss_fraction,
                "max_trades_per_day": args.max_trades_per_day,
                "cooldown_after_losses": args.cooldown_after_losses,
                "cooldown_minutes": args.cooldown_minutes,
            },
        },
    }
    out_json = Path(args.output_summary_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _print_report(summary, replay_stats)
    print(f"Trades CSV written: {args.output_trades_csv}")
    print(f"Summary JSON written: {args.output_summary_json}")


if __name__ == "__main__":
    main()
