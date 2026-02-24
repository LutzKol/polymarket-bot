#!/usr/bin/env python3
"""
Paper Trading Monitor - Oracle Lag Signal
Monitors live data for oracle lag signals and logs paper trades.
"""
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from trade_journal import log_trade, read_all_trades, daily_summary

# Signal Parameters
THRESHOLD = 0.05  # 5% oracle lag threshold
MIN_ASK = 0.40
MAX_ASK = 0.60
DEFAULT_STAKE = 3.00
MIN_EV = 0.03
COOLDOWN_LOSSES = 3
COOLDOWN_MINUTES = 30

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "person-a" / "data"
LIVE_CSV = DATA_DIR / "phase3_features_live.csv"
TRAINING_CSV = DATA_DIR / "phase3_features_training.csv"
POLL_INTERVAL = 5


def safe_float(val):
    try:
        return float(val) if val else None
    except:
        return None


def read_latest_data(filepath):
    if not filepath.exists():
        return None
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None


def calculate_ev(p_win, ask_price):
    fee = 0.25 * (ask_price * (1 - ask_price)) ** 2
    gross_profit = (1 / ask_price - 1)
    return p_win * gross_profit * (1 - fee) - (1 - p_win)


def check_cooldown():
    trades = read_all_trades()
    closed = [t for t in trades if t["status"] == "CLOSED"]
    if len(closed) < COOLDOWN_LOSSES:
        return False, None
    last_n = closed[-COOLDOWN_LOSSES:]
    if not all(t["outcome"] == "LOSS" for t in last_n):
        return False, None
    last_time = datetime.strptime(last_n[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
    cooldown_end = last_time + timedelta(minutes=COOLDOWN_MINUTES)
    if datetime.now() < cooldown_end:
        return True, cooldown_end
    return False, None


def generate_signal(oracle_lag_pct):
    if oracle_lag_pct is None:
        return "NONE", 0.0
    if oracle_lag_pct > THRESHOLD:
        return "UP", oracle_lag_pct
    elif oracle_lag_pct < -THRESHOLD:
        return "DOWN", abs(oracle_lag_pct)
    return "NONE", abs(oracle_lag_pct)


# Fixed win rate from backtest (5% threshold = 54.5% WR)
BACKTEST_WIN_RATE = 0.545


def print_alert(signal, lag, p_win, ev, ask=None):
    now = datetime.now().strftime("%H:%M:%S")
    print("")
    print("=" * 50)
    print(f"  SIGNAL: {signal} @ {now}")
    print("=" * 50)
    lag_pct = lag * 100
    print(f"  Oracle Lag:  {lag_pct:+.2f}%")
    print(f"  P(Win):      {p_win:.1%}")
    print(f"  EV:          {ev:+.2%}")
    if ask:
        print(f"  Ask Price:   {ask:.4f}")
    print("=" * 50)


def main():
    test_mode = "--test" in sys.argv
    csv_path = TRAINING_CSV if test_mode else LIVE_CSV

    print("=" * 50)
    print("PAPER TRADING - Oracle Lag Monitor")
    print("=" * 50)
    thresh_pct = THRESHOLD * 100
    mode_str = "TEST" if test_mode else "LIVE"
    print(f"  Threshold:     {thresh_pct:.1f}%")
    print(f"  Data Source:   {csv_path.name}")
    print(f"  Mode:          {mode_str}")
    print("=" * 50)
    print("")
    print("Ctrl+C to stop")
    print("")

    last_ts = None
    sig_count = 0

    try:
        while True:
            cool, cool_end = check_cooldown()
            if cool:
                rem = (cool_end - datetime.now()).seconds // 60
                print(f"[COOLDOWN] {rem} min remaining...", end="\r", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            data = read_latest_data(csv_path)
            if data is None:
                print("[WAIT] No data available...", end="\r", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            ts = data.get("timestamp_utc", "")
            if ts == last_ts:
                now_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{now_str}] Waiting for new data...", end="\r", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            last_ts = ts
            lag = safe_float(data.get("oracle_lag_pct"))
            pm_ask = safe_float(data.get("pm_best_ask"))

            signal, strength = generate_signal(lag)

            if signal == "NONE":
                lagv = lag * 100 if lag else 0
                now_str = datetime.now().strftime("%H:%M:%S")
                print(f"[{now_str}] Lag: {lagv:+.2f}%", end="\r", flush=True)
                time.sleep(POLL_INTERVAL)
                continue

            sig_count += 1
            p_win = BACKTEST_WIN_RATE  # Fixed 54.5% from backtest
            ask = pm_ask if pm_ask and MIN_ASK <= pm_ask <= MAX_ASK else 0.50
            ev = calculate_ev(p_win, ask)

            print_alert(signal, lag, p_win, ev, ask)

            if ev < MIN_EV:
                print(f"  [SKIP] EV {ev:.2%} < {MIN_EV:.2%}")
                continue

            if pm_ask and (pm_ask < MIN_ASK or pm_ask > MAX_ASK):
                print("  [SKIP] Ask out of range")
                continue

            print("  [TRADE] Logging...")
            tid = log_trade(signal, DEFAULT_STAKE, ask, p_win, ev)
            print(f"  [OK] {tid}")
            print("")
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("")
        print("")
        print("PAPER TRADING STOPPED")
        print(f"Signals detected: {sig_count}")
        daily_summary()


if __name__ == "__main__":
    main()
