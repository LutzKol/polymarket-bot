#!/usr/bin/env python3
"""Train a logistic regression model on labeled feature data.

Outputs a JSON model file compatible with ModelLoader in ev_engine.py.
Uses walk-forward validation to report Brier score before saving.

Usage:
    python3 train_model.py --input data/labeled_full.csv --output models/model.json
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

FEATURE_COLUMNS = [
    "oracle_lag_pct",
    "momentum_30s",
    "momentum_60s",
    "slope",
    "sigma_short",
    "sigma_long",
    "sigma_ratio",
    "obi",
    "cvd_60s",
    "tau",
    "tau_sq",
    "funding_rate",
    "pm_best_bid",
    "pm_best_ask",
    "pm_mid_prob",
    "pm_spread",
    "pm_obi",
]


def load_bucket_samples(csv_path: str) -> list[tuple[list[float], int]]:
    """Load labeled CSV, take one sample per bucket (last row), return (features, label) pairs."""
    buckets: dict[str, dict] = {}
    with open(csv_path, "r") as f:
        for row in csv.DictReader(f):
            bid = row.get("bucket_id", "")
            if bid:
                buckets[bid] = row  # keep last row per bucket

    samples = []
    skipped = 0
    for bid in sorted(buckets.keys(), key=int):
        row = buckets[bid]
        try:
            features = [float(row[col]) for col in FEATURE_COLUMNS]
            label = int(row["label"])
            samples.append((features, label))
        except (ValueError, KeyError):
            skipped += 1
            continue

    print(f"Loaded {len(samples)} bucket samples (skipped {skipped})")
    return samples


def sigmoid(z: float) -> float:
    if z < -500:
        return 0.0
    if z > 500:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def normalize(X_train: list[list[float]], X_test: list[list[float]]) -> tuple[list[list[float]], list[list[float]], list[float], list[float]]:
    """Z-score normalize using train stats. Returns normalized data + means/stds."""
    n_features = len(X_train[0])
    means = []
    stds = []
    for j in range(n_features):
        col = [x[j] for x in X_train]
        m = sum(col) / len(col)
        s = math.sqrt(sum((v - m) ** 2 for v in col) / len(col))
        means.append(m)
        stds.append(s if s > 0 else 1.0)

    X_train_n = [[(x[j] - means[j]) / stds[j] for j in range(n_features)] for x in X_train]
    X_test_n = [[(x[j] - means[j]) / stds[j] for j in range(n_features)] for x in X_test]
    return X_train_n, X_test_n, means, stds


def train_logistic(
    X: list[list[float]],
    y: list[int],
    lambda_reg: float = 0.1,
    lr: float = 0.05,
    epochs: int = 2000,
) -> list[float]:
    """Train logistic regression with L2 regularization. Returns [bias, w1, ..., wN]."""
    n_features = len(X[0])
    weights = [0.0] * (n_features + 1)
    n = len(X)

    for _ in range(epochs):
        gradients = [0.0] * len(weights)
        for i, x in enumerate(X):
            z = weights[0] + sum(weights[j + 1] * x[j] for j in range(n_features))
            pred = sigmoid(z)
            error = pred - y[i]
            gradients[0] += error
            for j in range(n_features):
                gradients[j + 1] += error * x[j]

        weights[0] -= lr * gradients[0] / n
        for j in range(1, len(weights)):
            weights[j] -= lr * (gradients[j] / n + lambda_reg * weights[j])

    return weights


def predict_proba(X: list[list[float]], weights: list[float]) -> list[float]:
    n_features = len(X[0])
    return [sigmoid(weights[0] + sum(weights[j + 1] * x[j] for j in range(n_features))) for x in X]


def brier_score(y_true: list[int], y_proba: list[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(y_proba, y_true)) / len(y_true)


def accuracy(y_true: list[int], y_proba: list[float]) -> float:
    correct = sum(1 for p, y in zip(y_proba, y_true) if (p > 0.5) == (y == 1))
    return correct / len(y_true)


def walk_forward_validate(
    samples: list[tuple[list[float], int]],
    train_frac: float = 0.6,
    n_folds: int = 5,
) -> list[dict]:
    """Walk-forward cross-validation."""
    n = len(samples)
    train_size = int(n * train_frac)
    test_size = (n - train_size) // n_folds
    if test_size < 10:
        test_size = max(10, (n - train_size) // 2)
        n_folds = min(n_folds, (n - train_size) // test_size)

    results = []
    for fold in range(n_folds):
        start = fold * test_size
        train_end = start + train_size
        test_end = train_end + test_size
        if test_end > n:
            break

        X_train = [s[0] for s in samples[start:train_end]]
        y_train = [s[1] for s in samples[start:train_end]]
        X_test = [s[0] for s in samples[train_end:test_end]]
        y_test = [s[1] for s in samples[train_end:test_end]]

        X_train_n, X_test_n, _, _ = normalize(X_train, X_test)
        weights = train_logistic(X_train_n, y_train)
        y_proba = predict_proba(X_test_n, weights)

        bs = brier_score(y_test, y_proba)
        acc = accuracy(y_test, y_proba)
        results.append({"fold": fold + 1, "brier": bs, "accuracy": acc, "test_size": len(y_test)})
        print(f"  Fold {fold + 1}: Brier={bs:.4f}  Acc={acc:.2%}  (n={len(y_test)})")

    return results


def train_final_model(
    samples: list[tuple[list[float], int]],
    output_path: str,
) -> None:
    """Train on all data with normalization baked into weights, save JSON."""
    X_all = [s[0] for s in samples]
    y_all = [s[1] for s in samples]

    # Compute normalization stats
    n_features = len(X_all[0])
    means = []
    stds = []
    for j in range(n_features):
        col = [x[j] for x in X_all]
        m = sum(col) / len(col)
        s = math.sqrt(sum((v - m) ** 2 for v in col) / len(col))
        means.append(m)
        stds.append(s if s > 0 else 1.0)

    # Normalize
    X_norm = [[(x[j] - means[j]) / stds[j] for j in range(n_features)] for x in X_all]

    # Train
    raw_weights = train_logistic(X_norm, y_all)

    # Bake normalization into weights so ModelLoader can use raw features:
    # z = bias + sum(w_j * (x_j - mean_j) / std_j)
    # z = (bias - sum(w_j * mean_j / std_j)) + sum((w_j / std_j) * x_j)
    baked_bias = raw_weights[0] - sum(raw_weights[j + 1] * means[j] / stds[j] for j in range(n_features))
    baked_weights = [baked_bias] + [raw_weights[j + 1] / stds[j] for j in range(n_features)]

    # Verify: predict on training data with baked weights should match normalized version
    y_proba_baked = [sigmoid(baked_weights[0] + sum(baked_weights[j + 1] * x[j] for j in range(n_features))) for x in X_all]
    y_proba_norm = predict_proba(X_norm, raw_weights)
    max_diff = max(abs(a - b) for a, b in zip(y_proba_baked, y_proba_norm))
    print(f"  Baked weights verification: max prediction diff = {max_diff:.2e}")

    train_brier = brier_score(y_all, y_proba_baked)
    train_acc = accuracy(y_all, y_proba_baked)
    print(f"  Training Brier={train_brier:.4f}  Acc={train_acc:.2%}")

    # Save
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    model_data = {
        "feature_columns": FEATURE_COLUMNS,
        "weights": baked_weights,
        "training_samples": len(samples),
        "training_brier": round(train_brier, 6),
        "training_accuracy": round(train_acc, 6),
    }
    with open(output_path, "w") as f:
        json.dump(model_data, f, indent=2)

    print(f"  Model saved to {output_path}")
    print(f"  Weights: {len(baked_weights)} (1 bias + {n_features} features)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train logistic regression model")
    parser.add_argument("--input", default="data/labeled_full.csv", help="Labeled CSV")
    parser.add_argument("--output", default="models/model.json", help="Output model JSON")
    parser.add_argument("--skip-validation", action="store_true", help="Skip walk-forward validation")
    args = parser.parse_args()

    samples = load_bucket_samples(args.input)
    if len(samples) < 50:
        print(f"Only {len(samples)} samples — need at least 50.")
        return 1

    if not args.skip_validation:
        print(f"\nWalk-forward validation ({len(samples)} buckets):")
        results = walk_forward_validate(samples)
        avg_brier = sum(r["brier"] for r in results) / len(results)
        avg_acc = sum(r["accuracy"] for r in results) / len(results)
        print(f"  Average: Brier={avg_brier:.4f}  Acc={avg_acc:.2%}")

        if avg_brier >= 0.25:
            print(f"\n  WARNING: Brier >= 0.25 (random baseline). Model may not have predictive power.")
            print(f"  Training anyway — you can evaluate on paper trades.\n")

    print(f"\nTraining final model on all {len(samples)} buckets:")
    train_final_model(samples, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
