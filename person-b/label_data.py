"""
Label data for ML training.
Creates labels based on price movement: 1 = Up, 0 = Down
"""
import csv


def label_data(input_file: str, output_file: str) -> None:
    # Load all rows
    with open(input_file, 'r', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    labeled_rows = []

    # Process all rows except the last one (no next_price available)
    for i in range(len(rows) - 1):
        current_price = float(rows[i]['price'])
        next_price = float(rows[i + 1]['price'])

        # Label: 1 if price goes up, 0 if down or equal
        label = 1 if next_price > current_price else 0

        labeled_rows.append({
            'roundId': rows[i]['roundId'],
            'timestamp': rows[i]['timestamp'],
            'price': current_price,
            'next_price': next_price,
            'label': label
        })

    # Write output
    with open(output_file, 'w', newline='') as f:
        fieldnames = ['roundId', 'timestamp', 'price', 'next_price', 'label']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(labeled_rows)

    # Statistics
    up_count = sum(1 for r in labeled_rows if r['label'] == 1)
    down_count = len(labeled_rows) - up_count
    total = len(labeled_rows)

    print(f"Labeled data saved to {output_file}")
    print(f"Total rows: {total}")
    print(f"\nDistribution:")
    print(f"  Up (1):   {up_count} ({100*up_count/total:.1f}%)")
    print(f"  Down (0): {down_count} ({100*down_count/total:.1f}%)")

    print(f"\nFirst 10 rows:")
    print("-" * 80)
    for row in labeled_rows[:10]:
        direction = "UP" if row['label'] == 1 else "DOWN"
        print(f"price: {row['price']:.2f} -> {row['next_price']:.2f} = {direction}")


if __name__ == '__main__':
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, 'chainlink_history.csv')
    output_path = os.path.join(script_dir, 'labeled_data.csv')
    label_data(input_path, output_path)
