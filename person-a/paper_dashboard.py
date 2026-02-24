#!/usr/bin/env python3
"""Quick CLI dashboard for paper trading results."""

import argparse
import csv
import json
import sys
from pathlib import Path


def load_trades(csv_path: str) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        print(f"No trades file found at {csv_path}")
        sys.exit(1)
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_dashboard(closed: list[dict]) -> str:
    """Build the dashboard string from closed trades."""
    if not closed:
        return "No closed trades yet."

    wins = [r for r in closed if r["won"] == "True"]
    losses = [r for r in closed if r["won"] == "False"]
    n = len(closed)
    w = len(wins)
    l = len(losses)
    win_rate = w / n * 100 if n else 0

    pnls = [float(r["pnl_usdc"]) for r in closed]
    total_pnl = sum(pnls)
    avg_pnl = total_pnl / n
    best = max(pnls)
    worst = min(pnls)
    best_row = closed[pnls.index(best)]
    worst_row = closed[pnls.index(worst)]

    sizes = [float(r["size_usdc"]) for r in closed]
    total_risked = sum(sizes)

    # Streaks
    max_win_streak = 0
    max_loss_streak = 0
    cur_win = 0
    cur_loss = 0
    for r in closed:
        if r["won"] == "True":
            cur_win += 1
            cur_loss = 0
            max_win_streak = max(max_win_streak, cur_win)
        else:
            cur_loss += 1
            cur_win = 0
            max_loss_streak = max(max_loss_streak, cur_loss)

    # Current streak
    cur_streak_type = None
    cur_streak_n = 0
    for r in reversed(closed):
        val = r["won"] == "True"
        if cur_streak_type is None:
            cur_streak_type = val
            cur_streak_n = 1
        elif val == cur_streak_type:
            cur_streak_n += 1
        else:
            break
    streak_label = f"{cur_streak_n}{'W' if cur_streak_type else 'L'}" if cur_streak_type is not None else "-"

    # Time range
    first_ts = closed[0].get("opened_at", "?")
    last_ts = closed[-1].get("closed_at", "?")

    # Profit factor
    gross_wins = sum(p for p in pnls if p > 0)
    gross_losses = abs(sum(p for p in pnls if p < 0))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else float("inf")

    pnl_emoji = "\U0001f4c8" if total_pnl >= 0 else "\U0001f4c9"

    return (
        f"{pnl_emoji} PAPER TRADING DASHBOARD\n"
        f"\n"
        f"Period: {first_ts}\n"
        f"     -> {last_ts}\n"
        f"\n"
        f"Record: {w}W / {l}L ({n} trades)\n"
        f"Win Rate: {win_rate:.1f}%\n"
        f"\n"
        f"Total PnL: ${total_pnl:+,.2f}\n"
        f"Avg PnL: ${avg_pnl:+,.2f}\n"
        f"Total Risked: ${total_risked:,.2f}\n"
        f"Profit Factor: {profit_factor:.2f}\n"
        f"\n"
        f"Best:  ${best:+,.2f} (#{best_row['trade_id']} {best_row['direction']})\n"
        f"Worst: ${worst:+,.2f} (#{worst_row['trade_id']} {worst_row['direction']})\n"
        f"\n"
        f"Win Streak: {max_win_streak} (best) | Current: {streak_label}\n"
        f"Loss Streak: {max_loss_streak} (worst)"
    )


def run(csv_path: str, telegram: bool = False, config_path: str = "config.json") -> None:
    rows = load_trades(csv_path)
    closed = [r for r in rows if r.get("status") == "CLOSED"]
    msg = build_dashboard(closed)

    if telegram:
        from phase2_pipeline.signal_alerts import send_telegram_message

        cfg = json.loads(Path(config_path).read_text())
        token = cfg["telegram_bot_token"]
        chat_id = cfg["telegram_chat_id"]
        send_telegram_message(token, chat_id, msg)
        print("Dashboard sent to Telegram!")
    else:
        print(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper trading dashboard")
    parser.add_argument(
        "--csv",
        default="data/paper_trades.csv",
        help="Path to paper_trades.csv",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="Send dashboard to Telegram instead of printing",
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (for Telegram credentials)",
    )
    args = parser.parse_args()
    run(args.csv, telegram=args.telegram, config_path=args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
