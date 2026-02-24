"""
Logistic Regression Model Training v3 - Full Feature Set
Aggregates 5-minute buckets from tick data, Walk-Forward Backtest
"""
import csv
import math
import os
import pickle
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Tuple

FEATURE_COLS = [
    'oracle_lag_pct', 'obi', 'cvd_60s', 'sigma_short', 'sigma_long',
    'sigma_ratio', 'momentum_30s', 'momentum_60s', 'slope',
    'pm_best_bid', 'pm_best_ask', 'pm_mid_prob', 'pm_spread', 'pm_obi'
]


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


def load_and_aggregate(filepath: str) -> List[Dict]:
    """Load tick data and aggregate to 5-minute buckets."""
    with open(filepath, 'r', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows):,} ticks")

    buckets = defaultdict(list)
    for row in rows:
        ts_str = row.get('timestamp_utc', '')
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
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
            'bucket_ts': bucket_ts,
            'oracle_price': last_valid([safe_float(t.get('oracle_price_usd')) for t in ticks]),
            'oracle_lag_pct': avg([safe_float(t.get('oracle_lag_pct')) for t in ticks]),
            'obi': avg([safe_float(t.get('obi')) for t in ticks]),
            'cvd_60s': avg([safe_float(t.get('cvd_60s')) for t in ticks]),
            'sigma_short': last_valid([safe_float(t.get('sigma_short')) for t in ticks]),
            'sigma_long': last_valid([safe_float(t.get('sigma_long')) for t in ticks]),
            'sigma_ratio': avg([safe_float(t.get('sigma_ratio')) for t in ticks]),
            'momentum_30s': avg([safe_float(t.get('momentum_30s')) for t in ticks]),
            'momentum_60s': avg([safe_float(t.get('momentum_60s')) for t in ticks]),
            'slope': avg([safe_float(t.get('slope')) for t in ticks]),
            'pm_best_bid': last_valid([safe_float(t.get('pm_best_bid')) for t in ticks]),
            'pm_best_ask': last_valid([safe_float(t.get('pm_best_ask')) for t in ticks]),
            'pm_mid_prob': last_valid([safe_float(t.get('pm_mid_prob')) for t in ticks]),
            'pm_spread': last_valid([safe_float(t.get('pm_spread')) for t in ticks]),
            'pm_obi': avg([safe_float(t.get('pm_obi')) for t in ticks]),
        }
        aggregated.append(agg)
    print(f"Aggregated to {len(aggregated)} 5-minute buckets")
    return aggregated


def create_labels(aggregated: List[Dict], filter_same: bool = True) -> Tuple[List[List[float]], List[int]]:
    """Create labels: Up=1 if next bucket price > current."""
    X, y = [], []
    skipped_same, skipped_missing = 0, 0

    for i in range(len(aggregated) - 1):
        curr, next_b = aggregated[i], aggregated[i + 1]
        curr_price, next_price = curr['oracle_price'], next_b['oracle_price']

        if curr_price is None or next_price is None:
            skipped_missing += 1
            continue

        if filter_same and abs(next_price - curr_price) < 0.01:
            skipped_same += 1
            continue

        features = []
        missing = False
        for col in FEATURE_COLS:
            val = curr.get(col)
            if val is None:
                missing = True
                break
            features.append(val)

        if missing:
            skipped_missing += 1
            continue

        label = 1 if next_price > curr_price else 0
        X.append(features)
        y.append(label)

    print(f"Valid samples: {len(X)}, Skipped SAME: {skipped_same}, Missing: {skipped_missing}")
    up = sum(y)
    print(f"Labels: {up} Up ({100*up/len(y):.1f}%), {len(y)-up} Down ({100*(len(y)-up)/len(y):.1f}%)")
    return X, y


def sigmoid(z: float) -> float:
    """Sigmoid function with overflow protection."""
    if z < -500:
        return 0.0
    if z > 500:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def train_logistic_regression(
    X: List[List[float]],
    y: List[int],
    lambda_reg: float = 0.1,
    lr: float = 0.1,
    epochs: int = 1000
) -> List[float]:
    """
    Train logistic regression with L2 regularization using gradient descent.
    Returns weights [w0, w1, w2, w3] where w0 is bias.
    """
    n_features = len(X[0])
    weights = [0.0] * (n_features + 1)  # +1 for bias

    for _ in range(epochs):
        gradients = [0.0] * len(weights)

        for i, x in enumerate(X):
            z = weights[0] + sum(weights[j+1] * x[j] for j in range(n_features))
            pred = sigmoid(z)
            error = pred - y[i]

            gradients[0] += error  # bias gradient
            for j in range(n_features):
                gradients[j+1] += error * x[j]

        # Update weights with L2 regularization
        n = len(X)
        weights[0] -= lr * gradients[0] / n  # no regularization on bias
        for j in range(1, len(weights)):
            weights[j] -= lr * (gradients[j] / n + lambda_reg * weights[j])

    return weights


def predict_proba(X: List[List[float]], weights: List[float]) -> List[float]:
    """Predict probabilities using trained weights."""
    n_features = len(X[0])
    probas = []
    for x in X:
        z = weights[0] + sum(weights[j+1] * x[j] for j in range(n_features))
        probas.append(sigmoid(z))
    return probas


def brier_score(y_true: List[int], y_proba: List[float]) -> float:
    """Calculate Brier Score (MSE of probabilities)."""
    return sum((p - y) ** 2 for p, y in zip(y_proba, y_true)) / len(y_true)


def accuracy(y_true: List[int], y_proba: List[float]) -> float:
    """Calculate accuracy."""
    y_pred = [1 if p > 0.5 else 0 for p in y_proba]
    correct = sum(1 for p, t in zip(y_pred, y_true) if p == t)
    return correct / len(y_true)


def win_rate(y_true: List[int], y_proba: List[float]) -> float:
    """Calculate win rate (precision for label=1)."""
    y_pred = [1 if p > 0.5 else 0 for p in y_proba]
    predicted_up = [(p, t) for p, t in zip(y_pred, y_true) if p == 1]
    if not predicted_up:
        return 0.0
    correct_up = sum(1 for p, t in predicted_up if t == 1)
    return correct_up / len(predicted_up)


def normalize_features(X_train: List[List[float]], X_test: List[List[float]]) -> Tuple[List[List[float]], List[List[float]], List[float], List[float]]:
    """Normalize features using train set statistics."""
    n_features = len(X_train[0])
    means, stds = [], []

    for j in range(n_features):
        col = [x[j] for x in X_train]
        mean = sum(col) / len(col)
        variance = sum((v - mean) ** 2 for v in col) / len(col)
        std = math.sqrt(variance) if variance > 0 else 1.0
        means.append(mean)
        stds.append(std)

    X_train_norm = [[(x[j] - means[j]) / stds[j] for j in range(n_features)] for x in X_train]
    X_test_norm = [[(x[j] - means[j]) / stds[j] for j in range(n_features)] for x in X_test]
    return X_train_norm, X_test_norm, means, stds


def isotonic_calibration(y_true: List[int], y_proba: List[float]) -> List[Tuple[float, float]]:
    """Fit isotonic regression using PAV algorithm."""
    pairs = sorted(zip(y_proba, y_true), key=lambda x: x[0])
    calibrated = [[pairs[i][0], float(pairs[i][1]), 1] for i in range(len(pairs))]
    i = 0
    while i < len(calibrated) - 1:
        if calibrated[i][1] / calibrated[i][2] > calibrated[i+1][1] / calibrated[i+1][2]:
            calibrated[i][1] += calibrated[i+1][1]
            calibrated[i][2] += calibrated[i+1][2]
            calibrated.pop(i+1)
            if i > 0:
                i -= 1
        else:
            i += 1
    return [(block[0], block[1] / block[2]) for block in calibrated]


def apply_calibration(y_proba: List[float], calibration_map: List[Tuple[float, float]]) -> List[float]:
    """Apply isotonic calibration to probabilities."""
    calibrated = []
    for p in y_proba:
        best_idx = 0
        for i, (thresh, _) in enumerate(calibration_map):
            if thresh <= p:
                best_idx = i
        calibrated.append(calibration_map[best_idx][1])
    return calibrated


def walk_forward_backtest(X: List[List[float]], y: List[int], train_size: int = 350, test_size: int = 128):
    """Walk-forward backtest with isotonic calibration."""
    results = []
    n_samples = len(X)
    max_folds = (n_samples - train_size) // test_size

    print(f"\nWalk-Forward Backtest (Train={train_size}, Test={test_size}, Folds={max_folds})")
    print("-" * 70)

    for fold in range(max_folds):
        start = fold * test_size
        train_end = start + train_size
        test_end = min(train_end + test_size, n_samples)
        if test_end > n_samples:
            break

        X_train, y_train = X[start:train_end], y[start:train_end]
        X_test, y_test = X[train_end:test_end], y[train_end:test_end]

        X_train_norm, X_test_norm, means, stds = normalize_features(X_train, X_test)

        # Split train: 75% core, 25% calibration
        cal_size = max(30, len(X_train_norm) // 4)
        X_core, y_core = X_train_norm[:-cal_size], y_train[:-cal_size]
        X_cal, y_cal = X_train_norm[-cal_size:], y_train[-cal_size:]

        weights = train_logistic_regression(X_core, y_core, lambda_reg=0.1)

        y_cal_proba = predict_proba(X_cal, weights)
        calibration_map = isotonic_calibration(y_cal, y_cal_proba)

        y_proba_raw = predict_proba(X_test_norm, weights)
        y_proba_cal = apply_calibration(y_proba_raw, calibration_map)

        bs = brier_score(y_test, y_proba_cal)
        bs_raw = brier_score(y_test, y_proba_raw)
        acc = accuracy(y_test, y_proba_cal)
        wr = win_rate(y_test, y_proba_cal)

        results.append({
            'fold': fold + 1, 'brier': bs, 'brier_raw': bs_raw,
            'accuracy': acc, 'win_rate': wr, 'weights': weights,
            'means': means, 'stds': stds, 'calibration_map': calibration_map
        })
        print(f"Fold {fold+1}: Brier={bs:.4f} (raw={bs_raw:.4f}), Acc={acc:.2%}, WinRate={wr:.2%}, n={len(y_test)}")

    return results


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(os.path.dirname(script_dir), 'person-a', 'data', 'phase3_features_training.csv')
    model_path = os.path.join(script_dir, 'model.pkl')

    print("=" * 70)
    print("Model Training v3 - Full Feature Set (14 Features)")
    print("=" * 70)

    print("\n[1] Loading and aggregating data...")
    aggregated = load_and_aggregate(data_path)

    print("\n[2] Creating labels...")
    X, y = create_labels(aggregated, filter_same=True)

    if len(X) < 100:
        print("ERROR: Not enough samples!")
        return

    # Adjust split based on available samples
    n_samples = len(X)
    if n_samples >= 478:
        train_size, test_size = 350, 128
    elif n_samples >= 400:
        train_size, test_size = 300, 100
    else:
        train_size, test_size = int(n_samples * 0.7), int(n_samples * 0.2)

    print(f"\n[3] Walk-Forward Backtest (adjusted for {n_samples} samples)...")
    results = walk_forward_backtest(X, y, train_size=train_size, test_size=test_size)

    avg_brier = sum(r['brier'] for r in results) / len(results)
    avg_brier_raw = sum(r['brier_raw'] for r in results) / len(results)
    avg_acc = sum(r['accuracy'] for r in results) / len(results)
    avg_wr = sum(r['win_rate'] for r in results) / len(results)

    print("-" * 70)
    print(f"AVERAGE: Brier={avg_brier:.4f} (raw={avg_brier_raw:.4f}), Acc={avg_acc:.2%}, WinRate={avg_wr:.2%}")
    print("-" * 70)

    print("\n[4] Training final model on all data...")
    X_norm, _, final_means, final_stds = normalize_features(X, X)
    cal_size = max(50, len(X_norm) // 4)
    final_weights = train_logistic_regression(X_norm[:-cal_size], y[:-cal_size], lambda_reg=0.1)
    y_cal_proba = predict_proba(X_norm[-cal_size:], final_weights)
    final_calibration = isotonic_calibration(y[-cal_size:], y_cal_proba)

    y_proba_all = apply_calibration(predict_proba(X_norm, final_weights), final_calibration)
    final_brier = brier_score(y, y_proba_all)
    final_acc = accuracy(y, y_proba_all)
    print(f"Final (in-sample): Brier={final_brier:.4f}, Acc={final_acc:.2%}")

    print("\n[5] Evaluation...")
    print(f"    Target: Brier < 0.24")
    print(f"    Result: Brier = {avg_brier:.4f}")

    if avg_brier < 0.24:
        print("    SUCCESS! Saving model...")
        model = {
            'weights': final_weights,
            'means': final_means,
            'stds': final_stds,
            'calibration_map': final_calibration,
            'feature_cols': FEATURE_COLS,
            'version': 'v3',
            'trained_at': datetime.now().isoformat(),
            'metrics': {
                'avg_brier': avg_brier,
                'avg_accuracy': avg_acc,
                'avg_win_rate': avg_wr,
                'n_samples': len(X),
                'n_folds': len(results)
            }
        }
        with open(model_path, 'wb') as f:
            pickle.dump(model, f)
        print(f"    Model saved to {model_path}")
    else:
        print(f"    FAILED - Brier {avg_brier:.4f} >= 0.24")
        print("    Model NOT saved.")

    return {'avg_brier': avg_brier, 'avg_acc': avg_acc, 'avg_wr': avg_wr, 'n': len(X), 'results': results}


if __name__ == '__main__':
    main()
