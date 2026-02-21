#!/usr/bin/env python3
"""Live feature dataset exporter for Strategy Analyst handoff."""

from __future__ import annotations

import argparse
import asyncio
import csv
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
    from phase2_pipeline.live_runner import Phase2LiveRunner, load_config
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
    from phase2_pipeline.live_runner import Phase2LiveRunner, load_config


BASE_COLUMNS = [
    "timestamp_utc",
    "oracle_round_id",
    "oracle_price_usd",
    "spot_price_usd",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10f}"
    return str(value)


def _open_writer(path: Path) -> tuple[csv.writer, any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    if new_file:
        writer.writerow(BASE_COLUMNS + FEATURE_COLUMNS)
        handle.flush()
    return writer, handle


async def export_loop(
    runner: Phase2LiveRunner,
    *,
    output_csv: Path,
    export_interval: float,
    duration_seconds: Optional[float],
    seconds_remaining: Optional[float],
) -> None:
    writer, handle = _open_writer(output_csv)
    extractor = FeatureExtractor()
    started = asyncio.get_running_loop().time()
    rows_written = 0

    runner_task = asyncio.create_task(runner.run())
    try:
        while True:
            if runner_task.done():
                exc = runner_task.exception()
                if exc is not None:
                    raise exc
                break

            snapshot = runner.state.snapshot(seconds_remaining=seconds_remaining)

            oracle_prices = snapshot.get("oracle_prices", [])
            spot_prices = snapshot.get("spot_prices", [])
            round_ids = snapshot.get("oracle_round_ids", [])

            # Skip export until we have at least one oracle AND spot price
            if not oracle_prices or not spot_prices:
                await asyncio.sleep(export_interval)
                continue

            features = extractor.extract(snapshot)

            oracle_price = oracle_prices[-1]
            spot_price = spot_prices[-1]
            round_id = round_ids[-1] if round_ids else None

            row = [
                _utc_now_iso(),
                _format_value(round_id),
                _format_value(oracle_price),
                _format_value(spot_price),
            ]
            row.extend(_format_value(features[col]) for col in FEATURE_COLUMNS)
            writer.writerow(row)
            handle.flush()
            rows_written += 1

            if duration_seconds is not None:
                elapsed = asyncio.get_running_loop().time() - started
                if elapsed >= duration_seconds:
                    print(f"[{_utc_now_iso()}] export duration reached -> stopping")
                    break

            await asyncio.sleep(export_interval)
    finally:
        await runner.shutdown()
        with suppress(Exception):
            await runner_task
        handle.close()
        print(f"[{_utc_now_iso()}] export finished, rows_written={rows_written}, output={output_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export live feature rows to CSV")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument(
        "--output-csv",
        default="data/phase3_features_live.csv",
        help="Output CSV path",
    )
    parser.add_argument("--export-interval", type=float, default=1.0, help="Export interval in seconds")
    parser.add_argument("--heartbeat-seconds", type=float, default=2.0, help="Runner heartbeat interval")
    parser.add_argument("--oracle-poll-seconds", type=float, default=None, help="Oracle poll interval override")
    parser.add_argument("--history-size", type=int, default=1800, help="State history size")
    parser.add_argument("--polymarket-token-id", default=None, help="Polymarket token id for /book polling")
    parser.add_argument("--polymarket-poll-seconds", type=float, default=None, help="Polymarket poll interval")
    parser.add_argument("--polymarket-base-url", default=None, help="Polymarket CLOB base URL")
    parser.add_argument("--funding-enabled", type=str, default=None, help="Enable funding poller: true/false")
    parser.add_argument("--funding-symbol", default=None, help="Funding symbol, e.g. BTCUSDT")
    parser.add_argument("--funding-poll-seconds", type=float, default=None, help="Funding poll interval")
    parser.add_argument("--funding-base-url", default=None, help="Funding API base URL")
    parser.add_argument(
        "--seconds-remaining",
        type=float,
        default=None,
        help="Optional fixed seconds_remaining for tau/tau_sq feature",
    )
    parser.add_argument("--duration-seconds", type=float, default=None, help="Optional max runtime")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    oracle_poll_seconds = (
        args.oracle_poll_seconds
        if args.oracle_poll_seconds is not None
        else float(config.get("oracle_poll_seconds", 5))
    )
    polymarket_token_id = args.polymarket_token_id or config.get("polymarket_token_id")
    polymarket_poll_seconds = (
        args.polymarket_poll_seconds
        if args.polymarket_poll_seconds is not None
        else float(config.get("polymarket_poll_seconds", 1.0))
    )
    polymarket_base_url = (
        args.polymarket_base_url
        if args.polymarket_base_url is not None
        else str(config.get("polymarket_base_url", "https://clob.polymarket.com"))
    )
    funding_enabled = config.get("funding_enabled", True)
    if args.funding_enabled is not None:
        funding_enabled = str(args.funding_enabled).strip().lower() in {"1", "true", "yes", "on"}
    funding_symbol = args.funding_symbol or str(config.get("funding_symbol", "BTCUSDT"))
    funding_poll_seconds = (
        args.funding_poll_seconds
        if args.funding_poll_seconds is not None
        else float(config.get("funding_poll_seconds", 30.0))
    )
    funding_base_url = (
        args.funding_base_url
        if args.funding_base_url is not None
        else str(config.get("funding_base_url", "https://fapi.binance.com"))
    )

    runner = Phase2LiveRunner(
        rpc_url=config["polygon_rpc_url"],
        chainlink_address=config.get("chainlink_address", "0xc907E116054Ad103354f2D350FD2514433D57F6f"),
        oracle_poll_seconds=oracle_poll_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
        history_size=args.history_size,
        polymarket_token_id=polymarket_token_id,
        polymarket_poll_seconds=polymarket_poll_seconds,
        polymarket_base_url=polymarket_base_url,
        funding_enabled=bool(funding_enabled),
        funding_symbol=funding_symbol,
        funding_poll_seconds=funding_poll_seconds,
        funding_base_url=funding_base_url,
    )

    try:
        asyncio.run(
            export_loop(
                runner,
                output_csv=Path(args.output_csv),
                export_interval=args.export_interval,
                duration_seconds=args.duration_seconds,
                seconds_remaining=args.seconds_remaining,
            )
        )
    except KeyboardInterrupt:
        print(f"\n[{_utc_now_iso()}] interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
