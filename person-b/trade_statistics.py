"""
Trade Statistics Calculator for 200-Trade Analysis.
Calculates Sharpe Ratio, Drawdown, Brier Score, and Kill-Switch recommendations.
"""
import csv
import math
import os
from datetime import datetime
from typing import List, Dict, Tuple


def load_trades(filepath: str) -> List[Dict]:
    """Load trades from CSV file."""
    trades = []
    with open(filepath, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trades.append({
                'timestamp': int(row['timestamp']),
                'market': row['market'],
                'ask_price': float(row['ask_price']),
                'stake': float(row['stake']),
                'p_win': float(row['p_win']),
                'outcome': int(row['outcome']),
                'pnl': float(row['pnl'])
            })
    return trades


def calc_basic_stats(trades: List[Dict]) -> Dict:
    """Calculate basic trading statistics."""
    total = len(trades)
    wins = sum(1 for t in trades if t['outcome'] == 1)
    losses = total - wins
    win_rate = wins / total if total > 0 else 0

    total_pnl = sum(t['pnl'] for t in trades)
    avg_pnl = total_pnl / total if total > 0 else 0

    avg_ask = sum(t['ask_price'] for t in trades) / total if total > 0 else 0
    avg_stake = sum(t['stake'] for t in trades) / total if total > 0 else 0

    return {
        'total_trades': total,
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'avg_ask': avg_ask,
        'avg_stake': avg_stake
    }


def calc_brier_score(trades: List[Dict]) -> float:
    """
    Calculate Brier Score (MSE of probabilities vs outcomes).
    Lower is better. 0.25 = random, <0.24 = usable model.
    """
    if not trades:
        return 0.0

    mse = sum((t['p_win'] - t['outcome']) ** 2 for t in trades) / len(trades)
    return mse


def calc_sharpe_ratio(trades: List[Dict], periods_per_year: int = 252 * 24 * 12) -> float:
    """
    Calculate Sharpe Ratio.

    Sharpe = (Avg PnL / Std PnL) * sqrt(periods_per_year)

    Default: 252 trading days * 24 hours * 12 five-minute periods = ~72,576
    """
    if len(trades) < 2:
        return 0.0

    pnls = [t['pnl'] for t in trades]
    avg_pnl = sum(pnls) / len(pnls)

    variance = sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)
    std_pnl = math.sqrt(variance)

    if std_pnl == 0:
        return 0.0

    sharpe = (avg_pnl / std_pnl) * math.sqrt(periods_per_year)
    return sharpe


def calc_drawdown(trades: List[Dict], starting_capital: float = 100.0) -> Dict:
    """
    Calculate drawdown metrics.

    Returns:
        - max_drawdown_usd: Maximum drawdown in dollars
        - max_drawdown_pct: Maximum drawdown as percentage
        - longest_losing_streak: Consecutive losses
        - current_streak: Current win/loss streak
    """
    if not trades:
        return {
            'max_drawdown_usd': 0.0,
            'max_drawdown_pct': 0.0,
            'longest_losing_streak': 0,
            'current_streak': 0
        }

    # Calculate cumulative equity curve
    equity = [starting_capital]
    for t in trades:
        equity.append(equity[-1] + t['pnl'])

    # Calculate max drawdown
    peak = starting_capital
    max_dd_usd = 0.0
    max_dd_pct = 0.0

    for eq in equity[1:]:
        if eq > peak:
            peak = eq
        drawdown = peak - eq
        drawdown_pct = drawdown / peak if peak > 0 else 0

        if drawdown > max_dd_usd:
            max_dd_usd = drawdown
            max_dd_pct = drawdown_pct

    # Calculate losing streaks
    current_streak = 0
    longest_losing = 0
    temp_losing = 0

    for t in trades:
        if t['outcome'] == 0:
            temp_losing += 1
            longest_losing = max(longest_losing, temp_losing)
        else:
            temp_losing = 0

    # Current streak (positive = wins, negative = losses)
    for t in reversed(trades):
        if current_streak == 0:
            current_streak = 1 if t['outcome'] == 1 else -1
        elif (current_streak > 0 and t['outcome'] == 1) or (current_streak < 0 and t['outcome'] == 0):
            current_streak += 1 if current_streak > 0 else -1
        else:
            break

    return {
        'max_drawdown_usd': max_dd_usd,
        'max_drawdown_pct': max_dd_pct,
        'longest_losing_streak': longest_losing,
        'current_streak': current_streak,
        'final_equity': equity[-1]
    }


def calc_kill_switch(trades: List[Dict], fee_rate: float = 0.0) -> Dict:
    """
    Calculate Kill-Switch recommendation.

    Break-Even Win Rate = Avg Ask Price / (1 - Fee)

    If current win rate falls below this, trading is -EV.
    """
    if not trades:
        return {
            'break_even_win_rate': 0.5,
            'current_win_rate': 0.0,
            'margin': 0.0,
            'recommendation': 'NO_DATA'
        }

    avg_ask = sum(t['ask_price'] for t in trades) / len(trades)
    break_even = avg_ask / (1 - fee_rate)

    current_wr = sum(1 for t in trades if t['outcome'] == 1) / len(trades)
    margin = current_wr - break_even

    # Recommendation based on margin
    if margin >= 0.05:
        rec = 'CONTINUE'
    elif margin >= 0.02:
        rec = 'CAUTION'
    elif margin >= 0:
        rec = 'WARNING'
    else:
        rec = 'STOP'

    return {
        'break_even_win_rate': break_even,
        'current_win_rate': current_wr,
        'margin': margin,
        'recommendation': rec,
        'avg_ask_price': avg_ask
    }


def generate_report(trades: List[Dict], starting_capital: float = 100.0) -> str:
    """Generate markdown report with all statistics."""
    basic = calc_basic_stats(trades)
    brier = calc_brier_score(trades)
    sharpe = calc_sharpe_ratio(trades)
    drawdown = calc_drawdown(trades, starting_capital)
    kill_switch = calc_kill_switch(trades)

    report = f"""# Trade Statistics Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 1. Basic Statistics

| Metric | Value |
|--------|-------|
| Total Trades | {basic['total_trades']} |
| Wins | {basic['wins']} |
| Losses | {basic['losses']} |
| **Win Rate** | **{basic['win_rate']:.2%}** |
| Total PnL | ${basic['total_pnl']:.2f} |
| Avg PnL/Trade | ${basic['avg_pnl']:.2f} |
| Avg Ask Price | {basic['avg_ask']:.3f} |
| Avg Stake | ${basic['avg_stake']:.2f} |

---

## 2. Model Calibration

| Metric | Value | Target |
|--------|-------|--------|
| **Brier Score** | **{brier:.4f}** | < 0.24 |
| Status | {'PASS' if brier < 0.24 else 'FAIL'} | - |

> Brier Score misst die Kalibrierung der Wahrscheinlichkeiten.
> 0.25 = Zufall, < 0.24 = nutzbares Modell.

---

## 3. Risk-Adjusted Return

| Metric | Value |
|--------|-------|
| **Sharpe Ratio** | **{sharpe:.2f}** |
| Interpretation | {'Excellent' if sharpe > 2 else 'Good' if sharpe > 1 else 'Acceptable' if sharpe > 0.5 else 'Poor' if sharpe > 0 else 'Negative'} |

> Sharpe = (Avg PnL / Std PnL) * sqrt(annualized periods)
> Annualisiert auf 5-Minuten Perioden (252 * 24 * 12)

---

## 4. Drawdown Analysis

| Metric | Value |
|--------|-------|
| Starting Capital | ${starting_capital:.2f} |
| Final Equity | ${drawdown['final_equity']:.2f} |
| **Max Drawdown ($)** | **${drawdown['max_drawdown_usd']:.2f}** |
| **Max Drawdown (%)** | **{drawdown['max_drawdown_pct']:.2%}** |
| Longest Losing Streak | {drawdown['longest_losing_streak']} trades |
| Current Streak | {abs(drawdown['current_streak'])} {'wins' if drawdown['current_streak'] > 0 else 'losses'} |

### Drawdown Limits Check

| Rule | Limit | Current | Status |
|------|-------|---------|--------|
| Max Daily Loss | 8% ($8) | {drawdown['max_drawdown_pct']:.2%} | {'PASS' if drawdown['max_drawdown_pct'] < 0.08 else 'FAIL'} |
| Cooldown Trigger | 3 losses | {drawdown['longest_losing_streak']} | {'TRIGGERED' if drawdown['longest_losing_streak'] >= 3 else 'OK'} |

---

## 5. Kill-Switch Analysis

| Metric | Value |
|--------|-------|
| Avg Ask Price | {kill_switch['avg_ask_price']:.3f} |
| **Break-Even Win Rate** | **{kill_switch['break_even_win_rate']:.2%}** |
| Current Win Rate | {kill_switch['current_win_rate']:.2%} |
| Margin | {kill_switch['margin']:+.2%} |
| **Recommendation** | **{kill_switch['recommendation']}** |

### Kill-Switch Interpretation

| Status | Meaning | Action |
|--------|---------|--------|
| CONTINUE | Margin >= 5% | Keep trading |
| CAUTION | Margin 2-5% | Monitor closely |
| WARNING | Margin 0-2% | Reduce stake |
| STOP | Margin < 0% | Stop trading immediately |

---

## 6. Summary

### Current Status: {'HEALTHY' if kill_switch['recommendation'] in ['CONTINUE', 'CAUTION'] and brier < 0.24 else 'AT RISK' if kill_switch['recommendation'] == 'WARNING' else 'CRITICAL'}

**Key Findings:**
- Win Rate {basic['win_rate']:.2%} vs Required {kill_switch['break_even_win_rate']:.2%} (Target: >54%)
- Brier Score {brier:.4f} {'meets' if brier < 0.24 else 'exceeds'} threshold of 0.24
- Max Drawdown {drawdown['max_drawdown_pct']:.2%} {'within' if drawdown['max_drawdown_pct'] < 0.08 else 'exceeds'} 8% limit
- ROI: {((drawdown['final_equity'] - starting_capital) / starting_capital):.2%}

---

*Report generated by trade_statistics.py*
*Project: Polymarket BTC 5-Min Oracle Lag Arbitrage*
"""
    return report


def print_summary(trades: List[Dict], starting_capital: float = 100.0) -> None:
    """Print summary to console."""
    basic = calc_basic_stats(trades)
    brier = calc_brier_score(trades)
    sharpe = calc_sharpe_ratio(trades)
    drawdown = calc_drawdown(trades, starting_capital)
    kill_switch = calc_kill_switch(trades)

    print("=" * 50)
    print("TRADE STATISTICS SUMMARY")
    print("=" * 50)
    print(f"\nTrades: {basic['total_trades']} | Wins: {basic['wins']} | Losses: {basic['losses']}")
    print(f"Win Rate: {basic['win_rate']:.2%} (Target: >54%)")
    print(f"Total PnL: ${basic['total_pnl']:.2f}")
    print(f"Avg PnL/Trade: ${basic['avg_pnl']:.2f}")
    print(f"\nBrier Score: {brier:.4f} ({'PASS' if brier < 0.24 else 'FAIL'} - Target: <0.24)")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    print(f"\nMax Drawdown: ${drawdown['max_drawdown_usd']:.2f} ({drawdown['max_drawdown_pct']:.2%})")
    print(f"Longest Losing Streak: {drawdown['longest_losing_streak']}")
    print(f"\nBreak-Even Win Rate: {kill_switch['break_even_win_rate']:.2%}")
    print(f"Kill-Switch: {kill_switch['recommendation']}")
    print("=" * 50)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    trades_path = os.path.join(script_dir, 'trades.csv')
    docs_dir = os.path.join(script_dir, 'docs')
    report_path = os.path.join(docs_dir, 'statistics_report.md')

    # Check if trades.csv exists
    if not os.path.exists(trades_path):
        print(f"ERROR: {trades_path} not found")
        print("Please ensure trades.csv exists with columns:")
        print("timestamp,market,ask_price,stake,p_win,outcome,pnl")
        return

    # Load trades
    print(f"Loading trades from {trades_path}...")
    trades = load_trades(trades_path)
    print(f"Loaded {len(trades)} trades")

    # Print summary to console
    print_summary(trades)

    # Generate and save report
    os.makedirs(docs_dir, exist_ok=True)
    report = generate_report(trades)

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport saved to: {report_path}")


if __name__ == '__main__':
    main()
