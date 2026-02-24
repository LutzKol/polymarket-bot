"""
Rule-Based Signal Backtesting
Tests oracle_lag_pct threshold for directional prediction
"""
import csv
import os
from datetime import datetime
from collections import defaultdict

def safe_float(val):
    try:
        return float(val) if val else None
    except:
        return None

def avg(vals):
    valid = [v for v in vals if v is not None]
    return sum(valid) / len(valid) if valid else None

def last_valid(vals):
    for v in reversed(vals):
        if v is not None:
            return v
    return None

def load_and_aggregate(filepath):
    with open(filepath, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows):,} ticks")
    
    buckets = defaultdict(list)
    for row in rows:
        ts_str = row.get("timestamp_utc", "")
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            bucket_minute = (dt.minute // 5) * 5
            bucket_key = dt.replace(minute=bucket_minute, second=0, microsecond=0)
            buckets[bucket_key].append(row)
        except:
            pass
    
    sorted_keys = sorted(buckets.keys())
    aggregated = []
    for bucket_ts in sorted_keys:
        ticks = buckets[bucket_ts]
        agg = {
            "bucket_ts": bucket_ts,
            "oracle_price": last_valid([safe_float(t.get("oracle_price_usd")) for t in ticks]),
            "oracle_lag_pct": avg([safe_float(t.get("oracle_lag_pct")) for t in ticks]),
        }
        aggregated.append(agg)
    print(f"Aggregated to {len(aggregated)} 5-minute buckets")
    return aggregated

def create_samples(aggregated):
    samples = []
    for i in range(len(aggregated) - 1):
        curr, next_b = aggregated[i], aggregated[i + 1]
        curr_price = curr["oracle_price"]
        next_price = next_b["oracle_price"]
        lag = curr["oracle_lag_pct"]
        
        if curr_price is None or next_price is None or lag is None:
            continue
        if abs(next_price - curr_price) < 0.01:
            continue
        
        label = 1 if next_price > curr_price else 0
        samples.append({"lag": lag, "label": label, "ts": curr["bucket_ts"]})
    return samples

def backtest_threshold(samples, threshold):
    signals = []
    for s in samples:
        lag = s["lag"]
        label = s["label"]
        
        if lag > threshold:
            signal = 1  # UP
            correct = (label == 1)
        elif lag < -threshold:
            signal = 0  # DOWN
            correct = (label == 0)
        else:
            continue  # NONE
        
        signals.append({"signal": signal, "label": label, "correct": correct, "lag": lag})
    
    if not signals:
        return {"threshold": threshold, "count": 0, "win_rate": 0, "brier": 1.0}
    
    correct_count = sum(1 for s in signals if s["correct"])
    win_rate = correct_count / len(signals)
    
    # Brier: treat signal as probability (1.0 for UP, 0.0 for DOWN)
    brier = sum((s["signal"] - s["label"]) ** 2 for s in signals) / len(signals)
    
    # Breakdown by direction
    up_signals = [s for s in signals if s["signal"] == 1]
    down_signals = [s for s in signals if s["signal"] == 0]
    up_wr = sum(1 for s in up_signals if s["correct"]) / len(up_signals) if up_signals else 0
    down_wr = sum(1 for s in down_signals if s["correct"]) / len(down_signals) if down_signals else 0
    
    return {
        "threshold": threshold,
        "count": len(signals),
        "win_rate": win_rate,
        "brier": brier,
        "up_signals": len(up_signals),
        "up_wr": up_wr,
        "down_signals": len(down_signals),
        "down_wr": down_wr
    }

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(os.path.dirname(script_dir), "person-a", "data", "phase3_features_training.csv")
    
    print("=" * 70)
    print("Rule-Based Signal Backtest")
    print("=" * 70)

    print("\n[1] Loading data...")
    aggregated = load_and_aggregate(data_path)

    print("\n[2] Creating samples...")
    samples = create_samples(aggregated)
    print(f"Valid samples: {len(samples)}")

    # Calculate days
    if samples:
        first_ts = samples[0]["ts"]
        last_ts = samples[-1]["ts"]
        days = (last_ts - first_ts).total_seconds() / 86400
        print(f"Time span: {days:.2f} days")
    else:
        days = 1

    print("\n[3] Testing thresholds...")
    print("-" * 70)
    # Test fine-grained thresholds from 0.35% to 7%
    thresholds = [0.0035, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06, 0.065, 0.07]
    results = []

    header = f"{'Threshold':>10} {'Signals':>8} {'Sig/Day':>8} {'WinRate':>8} {'Brier':>8} {'UP_WR':>8} {'DN_WR':>8}"
    print(header)
    print("-" * 70)

    for thresh in thresholds:
        r = backtest_threshold(samples, thresh)
        r["signals_per_day"] = r["count"] / days if days > 0 else 0
        results.append(r)
        cnt = r["count"]
        spd = r["signals_per_day"]
        wr = r["win_rate"] * 100
        br = r["brier"]
        uwr = r["up_wr"] * 100
        dwr = r["down_wr"] * 100
        print(f"{thresh*100:>9.2f}% {cnt:>8} {spd:>8.1f} {wr:>7.1f}% {br:>8.4f} {uwr:>7.1f}% {dwr:>7.1f}%")

    print("-" * 70)

    # Find best threshold with WR > 54%
    valid = [r for r in results if r["win_rate"] > 0.54 and r["count"] >= 10]
    if valid:
        best = max(valid, key=lambda x: x["count"])
        thr = best["threshold"] * 100
        cnt = best["count"]
        wr = best["win_rate"] * 100
        print(f"\nBest threshold (WR>54%, max signals): {thr:.2f}%")
        print(f"  Signals: {cnt}, Win Rate: {wr:.1f}%")
    else:
        print("\nNo threshold found with WR > 54% and >= 10 signals")
        best_wr = max(results, key=lambda x: x["win_rate"])
        thr = best_wr["threshold"] * 100
        wr = best_wr["win_rate"] * 100
        cnt = best_wr["count"]
        print(f"Best WR: {thr:.2f}% -> {wr:.1f}% ({cnt} signals)")

    return results, samples, days

if __name__ == "__main__":
    main()
