"""
Logistic Regression Model Training with Walk-Forward Backtest.
Features: oracle_lag_pct, sigma, momentum
"""
import csv
import math
import os
from typing import List, Dict, Tuple


def load_data(filepath: str) -> List[Dict]:
    """Load labeled data from CSV."""
    with open(filepath, 'r', newline='') as f:
        return list(csv.DictReader(f))


def compute_features(rows: List[Dict]) -> List[Dict]:
    """
    Compute features for each row:
    - oracle_lag_pct: (price - prev_price) / prev_price * 100
    - sigma: rolling std of last 10 prices
    - momentum: log(price / price_3_back)
    """
    prices = [float(r['price']) for r in rows]
    features = []

    for i in range(len(rows)):
        # Need at least 10 previous prices for sigma
        if i < 10:
            continue

        # oracle_lag_pct
        oracle_lag_pct = (prices[i] - prices[i-1]) / prices[i-1] * 100

        # sigma: rolling std of last 10 prices
        window = prices[i-9:i+1]  # 10 prices including current
        mean = sum(window) / len(window)
        variance = sum((p - mean) ** 2 for p in window) / len(window)
        sigma = math.sqrt(variance)

        # momentum: log(price / price_3_back)
        momentum = math.log(prices[i] / prices[i-3])

        features.append({
            'oracle_lag_pct': oracle_lag_pct,
            'sigma': sigma,
            'momentum': momentum,
            'label': int(rows[i]['label'])
        })

    return features


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


def normalize_features(X_train: List[List[float]], X_test: List[List[float]]) -> Tuple[List[List[float]], List[List[float]]]:
    """Normalize features using train set statistics."""
    n_features = len(X_train[0])
    means = []
    stds = []

    for j in range(n_features):
        col = [x[j] for x in X_train]
        mean = sum(col) / len(col)
        std = math.sqrt(sum((v - mean) ** 2 for v in col) / len(col))
        means.append(mean)
        stds.append(std if std > 0 else 1.0)

    X_train_norm = [[((x[j] - means[j]) / stds[j]) for j in range(n_features)] for x in X_train]
    X_test_norm = [[((x[j] - means[j]) / stds[j]) for j in range(n_features)] for x in X_test]

    return X_train_norm, X_test_norm


def walk_forward_backtest(features: List[Dict], train_size: int = 700, test_size: int = 100, n_folds: int = 5):
    """
    Walk-forward backtest with rolling windows.
    """
    results = []

    # Calculate max possible folds
    max_folds = (len(features) - train_size) // test_size
    actual_folds = min(n_folds, max_folds)
    print(f"(Max possible folds with data: {max_folds}, using: {actual_folds})")

    for fold in range(actual_folds):
        start = fold * test_size
        train_end = start + train_size
        test_end = train_end + test_size

        if test_end > len(features):
            break

        train_data = features[start:train_end]
        test_data = features[train_end:test_end]

        # Prepare data
        X_train = [[d['oracle_lag_pct'], d['sigma'], d['momentum']] for d in train_data]
        y_train = [d['label'] for d in train_data]
        X_test = [[d['oracle_lag_pct'], d['sigma'], d['momentum']] for d in test_data]
        y_test = [d['label'] for d in test_data]

        # Normalize
        X_train_norm, X_test_norm = normalize_features(X_train, X_test)

        # Train
        weights = train_logistic_regression(X_train_norm, y_train, lambda_reg=0.1)

        # Predict
        y_proba = predict_proba(X_test_norm, weights)

        # Metrics
        bs = brier_score(y_test, y_proba)
        acc = accuracy(y_test, y_proba)
        wr = win_rate(y_test, y_proba)

        results.append({
            'fold': fold + 1,
            'train_range': f"[{start}:{train_end}]",
            'test_range': f"[{train_end}:{test_end}]",
            'brier_score': bs,
            'accuracy': acc,
            'win_rate': wr,
            'weights': weights
        })

        print(f"Fold {fold + 1}: Brier={bs:.4f}, Acc={acc:.2%}, WinRate={wr:.2%}")

    return results


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, 'labeled_data.csv')

    print("Loading data...")
    rows = load_data(input_path)
    print(f"Loaded {len(rows)} rows")

    print("\nComputing features...")
    features = compute_features(rows)
    print(f"Features computed for {len(features)} rows (after dropping first 10)")

    print("\nWalk-Forward Backtest (Train=700, Test=100, 5 Folds):")
    print("-" * 60)
    results = walk_forward_backtest(features)

    # Averages
    avg_brier = sum(r['brier_score'] for r in results) / len(results)
    avg_acc = sum(r['accuracy'] for r in results) / len(results)
    avg_wr = sum(r['win_rate'] for r in results) / len(results)

    print("-" * 60)
    print(f"Average: Brier={avg_brier:.4f}, Acc={avg_acc:.2%}, WinRate={avg_wr:.2%}")

    # Save results for report generation
    return results, avg_brier, avg_acc, avg_wr


if __name__ == '__main__':
    main()
