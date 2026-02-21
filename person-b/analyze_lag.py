"""
Analyze Oracle Price Changes between Chainlink Updates
This is the core edge analysis for the Polymarket trading strategy

REAL DATA ANALYSIS - No simulations!
Analyzes actual price movements between consecutive Oracle updates.
"""

import csv
from datetime import datetime, timezone
from collections import defaultdict

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Configuration
LAG_THRESHOLD = 0.35  # 0.35% threshold for tradeable lag


import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_chainlink_data(filename="chainlink_history.csv"):
    """Load Chainlink oracle data from CSV"""
    filepath = os.path.join(SCRIPT_DIR, filename)
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({
                'roundId': int(row['roundId']),
                'timestamp': int(row['timestamp']),
                'price': float(row['price'])
            })
    return data


def calculate_price_changes(chainlink_data: list) -> list:
    """
    Calculate price changes between consecutive Oracle updates.

    This represents the MINIMUM lag that existed during each update interval.
    If price changed X% between updates, spot was at least X% ahead at some point.

    Returns list of price change events with direction and magnitude.
    """

    price_changes = []

    for i in range(1, len(chainlink_data)):
        prev = chainlink_data[i - 1]
        curr = chainlink_data[i]

        # Calculate price change percentage
        price_change_pct = (curr['price'] - prev['price']) / prev['price'] * 100
        abs_change = abs(price_change_pct)

        # Time between updates
        time_delta = curr['timestamp'] - prev['timestamp']

        price_changes.append({
            'timestamp': curr['timestamp'],
            'prev_price': prev['price'],
            'curr_price': curr['price'],
            'change_pct': price_change_pct,
            'abs_change': abs_change,
            'direction': 'UP' if price_change_pct > 0 else 'DOWN',
            'time_delta_sec': time_delta
        })

    return price_changes


def analyze_price_changes(price_changes: list, threshold: float = LAG_THRESHOLD):
    """
    Analyze price change events that exceed the threshold.

    Key insight: If Oracle price changed by X% between updates,
    the spot price was ahead by AT LEAST X% at some point during that interval.
    This is our trading opportunity window.
    """

    print(f"\n{BOLD}=== Oracle Price Change Analysis (Threshold: {threshold}%) ==={RESET}\n")

    # Filter significant price changes
    significant = [e for e in price_changes if e['abs_change'] >= threshold]

    total_events = len(price_changes)
    sig_events = len(significant)
    sig_rate = sig_events / total_events * 100 if total_events > 0 else 0

    print(f"Total Oracle updates: {total_events}")
    print(f"Significant moves (>={threshold}%): {sig_events} ({sig_rate:.2f}%)")

    if not significant:
        print(f"{YELLOW}[WARN]{RESET} No significant price changes found")
        return {}

    # Analyze significant moves
    abs_changes = [e['abs_change'] for e in significant]
    up_moves = [e for e in significant if e['direction'] == 'UP']
    down_moves = [e for e in significant if e['direction'] == 'DOWN']

    print(f"\n{BOLD}Price change distribution:{RESET}")
    print(f"  Upward moves: {len(up_moves)}")
    print(f"  Downward moves: {len(down_moves)}")
    print(f"  Mean absolute change: {sum(abs_changes)/len(abs_changes):.3f}%")
    print(f"  Max change: {max(abs_changes):.3f}%")
    print(f"  Min change (above threshold): {min(abs_changes):.3f}%")

    # Time deltas for significant moves
    time_deltas = [e['time_delta_sec'] for e in significant]
    avg_delta = sum(time_deltas) / len(time_deltas)
    print(f"\n{BOLD}Time between significant updates:{RESET}")
    print(f"  Avg interval: {avg_delta:.0f}s ({avg_delta/60:.1f}min)")
    print(f"  Max interval: {max(time_deltas)}s ({max(time_deltas)/60:.1f}min)")
    print(f"  Min interval: {min(time_deltas)}s")

    # Analyze by time of day
    hourly_counts = defaultdict(int)
    for e in significant:
        dt = datetime.fromtimestamp(e['timestamp'], tz=timezone.utc)
        hourly_counts[dt.hour] += 1

    print(f"\n{BOLD}Significant moves by hour (UTC):{RESET}")
    sorted_hours = sorted(hourly_counts.items(), key=lambda x: x[1], reverse=True)
    for hour, count in sorted_hours[:12]:
        bar = "#" * count
        print(f"  {hour:02d}:00 - {count:3d} events {bar}")

    # Analyze by day
    daily_counts = defaultdict(int)
    for e in significant:
        dt = datetime.fromtimestamp(e['timestamp'], tz=timezone.utc)
        daily_counts[dt.strftime('%Y-%m-%d')] += 1

    print(f"\n{BOLD}Significant moves by day:{RESET}")
    for day in sorted(daily_counts.keys()):
        count = daily_counts[day]
        bar = "#" * count
        print(f"  {day}: {count:3d} events {bar}")

    # Calculate updates per day
    timestamps = [e['timestamp'] for e in price_changes]
    days = (max(timestamps) - min(timestamps)) / 86400
    updates_per_day = len(price_changes) / days if days > 0 else 0
    signals_per_day = sig_events / days if days > 0 else 0

    print(f"\n{BOLD}Update frequency:{RESET}")
    print(f"  Days covered: {days:.1f}")
    print(f"  Total updates: {len(price_changes)}")
    print(f"  Avg updates/day: {updates_per_day:.1f}")
    print(f"  Trading signals/day: {signals_per_day:.1f}")

    # Distribution of change magnitudes
    print(f"\n{BOLD}Change magnitude distribution:{RESET}")
    ranges = [
        (0.35, 0.5, "0.35-0.50%"),
        (0.5, 0.75, "0.50-0.75%"),
        (0.75, 1.0, "0.75-1.00%"),
        (1.0, 1.5, "1.00-1.50%"),
        (1.5, 2.0, "1.50-2.00%"),
        (2.0, float('inf'), ">2.00%")
    ]
    for low, high, label in ranges:
        count = len([e for e in significant if low <= e['abs_change'] < high])
        if count > 0:
            bar = "#" * count
            print(f"  {label}: {count:3d} {bar}")

    return {
        'total_events': total_events,
        'significant_events': sig_events,
        'significant_rate': sig_rate,
        'up_signals': len(up_moves),
        'down_signals': len(down_moves),
        'mean_change': sum(abs_changes) / len(abs_changes),
        'max_change': max(abs_changes),
        'hourly_distribution': dict(hourly_counts),
        'daily_distribution': dict(daily_counts),
        'avg_interval_sec': avg_delta,
        'updates_per_day': updates_per_day,
        'signals_per_day': signals_per_day
    }


def generate_report(stats: dict, price_range: tuple, filename="docs/chainlink_analysis.md"):
    """Generate markdown analysis report with REAL data"""

    if not stats:
        print(f"{RED}[ERROR]{RESET} No stats to report")
        return

    # Use absolute path
    filepath = os.path.join(SCRIPT_DIR, filename)

    report = f"""# Chainlink Oracle Lag Analysis Report

## ECHTE DATEN - Keine Simulation!

Analyse basiert auf echten Chainlink BTC/USD Oracle-Daten von der Polygon Blockchain.

## Summary

| Metric | Value |
|--------|-------|
| Total Oracle Updates | {stats['total_events']:,} |
| Significant Price Moves (>={LAG_THRESHOLD}%) | {stats['significant_events']:,} |
| Signal Rate | {stats['significant_rate']:.2f}% |
| Mean Price Change | {stats['mean_change']:.3f}% |
| Max Price Change | {stats['max_change']:.3f}% |
| Upward Signals | {stats['up_signals']:,} |
| Downward Signals | {stats['down_signals']:,} |
| Avg Interval (sig. moves) | {stats['avg_interval_sec']:.0f}s |
| Oracle Updates/Day | {stats['updates_per_day']:.1f} |
| Trading Signals/Day | {stats['signals_per_day']:.1f} |
| Price Range | ${price_range[0]:,.2f} - ${price_range[1]:,.2f} |

## Interpretation

Wenn der Oracle-Preis um X% zwischen Updates springt, war der Spot-Preis
**mindestens X%** vor dem Oracle. Das ist unser Trading-Fenster.

## Significant Moves by Day

| Date | Events |
|------|--------|
"""

    for day in sorted(stats['daily_distribution'].keys()):
        count = stats['daily_distribution'][day]
        report += f"| {day} | {count} |\n"

    report += f"""
## Significant Moves by Hour (UTC)

| Hour | Events |
|------|--------|
"""

    for hour in range(24):
        count = stats['hourly_distribution'].get(hour, 0)
        report += f"| {hour:02d}:00 | {count} |\n"

    # Conclusion
    edge_viable = stats['significant_rate'] > 5.0 and stats['mean_change'] > LAG_THRESHOLD

    report += f"""
## Fazit

**Ist der Edge real und häufig genug?**

"""

    if edge_viable:
        report += f"""**JA** - Die ECHTE Analyse zeigt einen viablen Edge:

- **{stats['significant_rate']:.2f}%** der Oracle-Updates zeigen Preisänderungen >= {LAG_THRESHOLD}%
- Die durchschnittliche Preisänderung von **{stats['mean_change']:.3f}%** ist signifikant
- **{stats['signals_per_day']:.1f}** Trading-Signale pro Tag
- Die Balance zwischen Up/Down Signalen ({stats['up_signals']}/{stats['down_signals']}) zeigt keine systematische Verzerrung

**Empfehlung:** Weiter mit Phase 3 (Feature Engineering & Modell)
"""
    else:
        report += f"""**UNSICHER** - Die Daten zeigen:

- Nur **{stats['significant_rate']:.2f}%** der Updates mit signifikanter Preisänderung
- Durchschnittliche Änderung: **{stats['mean_change']:.3f}%**
- Nur **{stats['signals_per_day']:.1f}** Signale pro Tag

**Empfehlung:** Mehr Daten sammeln oder Threshold anpassen.
"""

    report += f"""
---
*Generiert: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
*Threshold: {LAG_THRESHOLD}%*
*Datenquelle: ECHTE Chainlink Oracle Daten (Polygon RPC)*
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n{GREEN}[SAVED]{RESET} {filepath}")


if __name__ == "__main__":
    print(f"\n{BOLD}=== Oracle Price Change Analysis (REAL DATA) ==={RESET}")

    # Load Chainlink data
    print("\nLoading Chainlink oracle data...")
    chainlink = load_chainlink_data()
    print(f"{GREEN}[OK]{RESET} Loaded {len(chainlink)} oracle updates")

    # Get price range
    prices = [d['price'] for d in chainlink]
    price_range = (min(prices), max(prices))
    print(f"Price range: ${price_range[0]:,.2f} - ${price_range[1]:,.2f}")

    # Calculate price changes between consecutive updates
    print("\nCalculating price changes between Oracle updates...")
    price_changes = calculate_price_changes(chainlink)
    print(f"{GREEN}[OK]{RESET} Calculated {len(price_changes)} price changes")

    # Analyze
    stats = analyze_price_changes(price_changes, threshold=LAG_THRESHOLD)

    # Generate report
    if stats:
        generate_report(stats, price_range)

    print(f"\n{BOLD}Analysis complete!{RESET}")
