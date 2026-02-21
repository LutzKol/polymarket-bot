"""
Isotonic Calibration for Logistic Regression Model.
Compares calibrated vs uncalibrated probabilities.
"""
import os
from typing import List, Tuple
from train_model import (
    load_data, compute_features, normalize_features,
    train_logistic_regression, predict_proba, brier_score
)


def isotonic_regression_fit(probas: List[float], labels: List[int]) -> List[Tuple[float, float]]:
    """
    Fit isotonic regression using Pool Adjacent Violators (PAV) algorithm.
    Returns list of (threshold, calibrated_value) pairs for interpolation.
    """
    # Sort by predicted probability
    pairs = sorted(zip(probas, labels), key=lambda x: x[0])
    n = len(pairs)

    # Initialize blocks: each point is its own block
    # Block: (start_idx, end_idx, sum_labels, count, mean_proba)
    blocks = []
    for i, (p, y) in enumerate(pairs):
        blocks.append({
            'start': i,
            'end': i,
            'sum_y': y,
            'count': 1,
            'mean_p': p,
            'value': y  # calibrated value = mean of labels in block
        })

    # PAV: merge adjacent blocks that violate monotonicity
    changed = True
    while changed:
        changed = False
        new_blocks = []
        i = 0
        while i < len(blocks):
            if i + 1 < len(blocks) and blocks[i]['value'] > blocks[i + 1]['value']:
                # Merge blocks i and i+1
                merged = {
                    'start': blocks[i]['start'],
                    'end': blocks[i + 1]['end'],
                    'sum_y': blocks[i]['sum_y'] + blocks[i + 1]['sum_y'],
                    'count': blocks[i]['count'] + blocks[i + 1]['count'],
                    'mean_p': (blocks[i]['mean_p'] * blocks[i]['count'] +
                               blocks[i + 1]['mean_p'] * blocks[i + 1]['count']) /
                              (blocks[i]['count'] + blocks[i + 1]['count']),
                    'value': (blocks[i]['sum_y'] + blocks[i + 1]['sum_y']) /
                             (blocks[i]['count'] + blocks[i + 1]['count'])
                }
                new_blocks.append(merged)
                i += 2
                changed = True
            else:
                new_blocks.append(blocks[i])
                i += 1
        blocks = new_blocks

    # Create mapping: (proba_threshold, calibrated_value)
    mapping = []
    for block in blocks:
        # Use mean probability of block as threshold
        mapping.append((block['mean_p'], block['value']))

    return mapping


def isotonic_regression_predict(probas: List[float], mapping: List[Tuple[float, float]]) -> List[float]:
    """
    Apply isotonic calibration mapping to new probabilities.
    Uses linear interpolation between mapping points.
    """
    if not mapping:
        return probas

    calibrated = []
    for p in probas:
        # Find surrounding mapping points
        if p <= mapping[0][0]:
            calibrated.append(mapping[0][1])
        elif p >= mapping[-1][0]:
            calibrated.append(mapping[-1][1])
        else:
            # Linear interpolation
            for i in range(len(mapping) - 1):
                if mapping[i][0] <= p <= mapping[i + 1][0]:
                    t = (p - mapping[i][0]) / (mapping[i + 1][0] - mapping[i][0]) if mapping[i + 1][0] != mapping[i][0] else 0
                    val = mapping[i][1] + t * (mapping[i + 1][1] - mapping[i][1])
                    calibrated.append(val)
                    break
            else:
                calibrated.append(p)  # fallback

    return calibrated


def compute_calibration_curve(probas: List[float], labels: List[int], n_bins: int = 10) -> Tuple[List[float], List[float], List[int]]:
    """
    Compute calibration curve data.
    Returns: (mean_predicted, fraction_positive, bin_counts)
    """
    bins = [[] for _ in range(n_bins)]

    for p, y in zip(probas, labels):
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append((p, y))

    mean_predicted = []
    fraction_positive = []
    bin_counts = []

    for bin_data in bins:
        if bin_data:
            mean_p = sum(p for p, y in bin_data) / len(bin_data)
            frac_pos = sum(y for p, y in bin_data) / len(bin_data)
            mean_predicted.append(mean_p)
            fraction_positive.append(frac_pos)
            bin_counts.append(len(bin_data))
        else:
            mean_predicted.append(None)
            fraction_positive.append(None)
            bin_counts.append(0)

    return mean_predicted, fraction_positive, bin_counts


def plot_calibration_curve(
    uncal_mean: List[float], uncal_frac: List[float],
    cal_mean: List[float], cal_frac: List[float],
    output_path: str
):
    """Create and save calibration curve plot."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 6))

    # Perfect calibration (diagonal)
    ax.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration', linewidth=2)

    # Uncalibrated
    uncal_x = [x for x in uncal_mean if x is not None]
    uncal_y = [y for y in uncal_frac if y is not None]
    if uncal_x and uncal_y:
        ax.plot(uncal_x, uncal_y, 'ro-', label='Uncalibrated', linewidth=2, markersize=8)

    # Calibrated
    cal_x = [x for x in cal_mean if x is not None]
    cal_y = [y for y in cal_frac if y is not None]
    if cal_x and cal_y:
        ax.plot(cal_x, cal_y, 'bs-', label='Calibrated (Isotonic)', linewidth=2, markersize=8)

    ax.set_xlabel('Mean Predicted Probability', fontsize=12)
    ax.set_ylabel('Fraction of Positives', fontsize=12)
    ax.set_title('Calibration Curve: Uncalibrated vs Isotonic', fontsize=14)
    ax.legend(loc='lower right', fontsize=10)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Calibration curve saved to {output_path}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, 'labeled_data.csv')
    plot_path = os.path.join(script_dir, 'docs', 'calibration_curve.png')

    print("=" * 60)
    print("ISOTONIC CALIBRATION")
    print("=" * 60)

    # Load and prepare data
    print("\nLoading data...")
    rows = load_data(input_path)
    features = compute_features(rows)
    print(f"Features: {len(features)} rows")

    # Use last fold configuration: Train [100:800], Test [800:900]
    train_data = features[100:800]
    test_data = features[800:900]

    print(f"Train: [100:800] ({len(train_data)} rows)")
    print(f"Test:  [800:900] ({len(test_data)} rows)")

    # Prepare training data
    X_train = [[d['oracle_lag_pct'], d['sigma'], d['momentum']] for d in train_data]
    y_train = [d['label'] for d in train_data]

    # Prepare full test data
    X_test = [[d['oracle_lag_pct'], d['sigma'], d['momentum']] for d in test_data]
    y_test = [d['label'] for d in test_data]

    # Normalize
    X_train_norm, X_test_norm = normalize_features(X_train, X_test)

    # Train logistic regression
    print("\nTraining logistic regression...")
    weights = train_logistic_regression(X_train_norm, y_train, lambda_reg=0.1)

    # Get uncalibrated predictions on full test set
    y_proba_uncal = predict_proba(X_test_norm, weights)

    # Split test set for calibration: [800:850] for cal_train, [850:900] for cal_test
    cal_train_probas = y_proba_uncal[:50]
    cal_train_labels = y_test[:50]
    cal_test_probas = y_proba_uncal[50:]
    cal_test_labels = y_test[50:]

    print(f"\nCalibration split:")
    print(f"  Cal Train: 50 samples (indices 0-49 of test)")
    print(f"  Cal Test:  50 samples (indices 50-99 of test)")

    # Fit isotonic regression on calibration train set
    print("\nFitting isotonic regression...")
    iso_mapping = isotonic_regression_fit(cal_train_probas, cal_train_labels)
    print(f"  Mapping points: {len(iso_mapping)}")

    # Calibrate probabilities on calibration test set
    cal_test_probas_calibrated = isotonic_regression_predict(cal_test_probas, iso_mapping)

    # Compute Brier scores
    brier_before = brier_score(cal_test_labels, cal_test_probas)
    brier_after = brier_score(cal_test_labels, cal_test_probas_calibrated)

    print("\n" + "-" * 60)
    print("RESULTS (on calibration test set, n=50)")
    print("-" * 60)
    print(f"Brier Score BEFORE calibration: {brier_before:.4f}")
    print(f"Brier Score AFTER calibration:  {brier_after:.4f}")
    print(f"Improvement: {(brier_before - brier_after):.4f} ({(brier_before - brier_after) / brier_before * 100:.1f}%)")

    # Compute calibration curves
    print("\nComputing calibration curves...")
    uncal_mean, uncal_frac, _ = compute_calibration_curve(cal_test_probas, cal_test_labels, n_bins=5)
    cal_mean, cal_frac, _ = compute_calibration_curve(cal_test_probas_calibrated, cal_test_labels, n_bins=5)

    # Create plot
    plot_calibration_curve(uncal_mean, uncal_frac, cal_mean, cal_frac, plot_path)

    return {
        'brier_before': brier_before,
        'brier_after': brier_after,
        'improvement': brier_before - brier_after
    }


if __name__ == '__main__':
    main()
