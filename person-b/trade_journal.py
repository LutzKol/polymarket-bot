#!/usr/bin/env python3
"""
Trade Journal - Manuelles Trade-Tracking mit CSV-Speicherung

Funktionen:
- log_trade(): Neuen Trade eintragen
- resolve_trade(): Trade aufloesen (WIN/LOSS)
- daily_summary(): Tagesuebersicht
"""

import csv
import os
from datetime import datetime
from pathlib import Path

# Konstanten
STARTING_CAPITAL = 100.0
MAX_DAILY_LOSS_PERCENT = 0.08  # 8%

# Pfade
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
TRADES_FILE = DATA_DIR / "trades.csv"

# CSV Spalten
CSV_COLUMNS = [
    "id", "timestamp", "direction", "stake", "ask_price",
    "p_win", "ev", "status", "outcome", "pnl", "fee"
]


def ensure_csv_exists():
    """Stelle sicher dass CSV existiert mit Header"""
    DATA_DIR.mkdir(exist_ok=True)
    if not TRADES_FILE.exists():
        with open(TRADES_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)


def calculate_fee(ask_price: float) -> float:
    """
    Berechne Fee nach Polymarket Formel
    fee = 0.25 * (ask * (1-ask))^2
    """
    return 0.25 * (ask_price * (1 - ask_price)) ** 2


def get_next_trade_id() -> str:
    """Generiere naechste Trade-ID (T001, T002, ...)"""
    ensure_csv_exists()

    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        trades = list(reader)

    if not trades:
        return "T001"

    # Finde hoechste ID
    max_id = 0
    for trade in trades:
        try:
            num = int(trade["id"][1:])
            max_id = max(max_id, num)
        except (ValueError, KeyError):
            pass

    return f"T{max_id + 1:03d}"


def read_all_trades() -> list:
    """Lese alle Trades aus CSV"""
    ensure_csv_exists()

    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_all_trades(trades: list):
    """Schreibe alle Trades in CSV"""
    ensure_csv_exists()

    with open(TRADES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(trades)


def get_current_bankroll() -> float:
    """Berechne aktuellen Bankroll basierend auf allen PnL"""
    trades = read_all_trades()

    total_pnl = 0.0
    for trade in trades:
        if trade["status"] == "CLOSED" and trade["pnl"]:
            total_pnl += float(trade["pnl"])

    return STARTING_CAPITAL + total_pnl


def log_trade(direction: str, stake: float, ask_price: float,
              p_win: float, ev: float) -> str:
    """
    Neuen Trade eintragen

    Args:
        direction: UP oder DOWN
        stake: Einsatz in $
        ask_price: Kaufpreis (0.00 - 1.00)
        p_win: Geschaetzte Gewinnwahrscheinlichkeit
        ev: Expected Value

    Returns:
        Trade-ID
    """
    ensure_csv_exists()

    # Validierung
    direction = direction.upper()
    if direction not in ["UP", "DOWN"]:
        raise ValueError("Direction muss UP oder DOWN sein")

    if not 0 < ask_price < 1:
        raise ValueError("ask_price muss zwischen 0 und 1 sein")

    if stake <= 0:
        raise ValueError("stake muss positiv sein")

    # Trade erstellen
    trade_id = get_next_trade_id()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trade = {
        "id": trade_id,
        "timestamp": timestamp,
        "direction": direction,
        "stake": f"{stake:.2f}",
        "ask_price": f"{ask_price:.4f}",
        "p_win": f"{p_win:.4f}",
        "ev": f"{ev:.4f}",
        "status": "OPEN",
        "outcome": "",
        "pnl": "",
        "fee": ""
    }

    # Append zu CSV
    with open(TRADES_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(trade)

    print(f"Trade {trade_id} erfasst:")
    print(f"  Direction: {direction}")
    print(f"  Stake: ${stake:.2f}")
    print(f"  Ask Price: {ask_price:.4f}")
    print(f"  P(Win): {p_win:.2%}")
    print(f"  EV: {ev:.2%}")
    print(f"  Status: OPEN")

    return trade_id


def resolve_trade(trade_id: str, outcome: str) -> dict:
    """
    Trade aufloesen wenn Ergebnis bekannt

    Args:
        trade_id: Trade-ID (z.B. T001)
        outcome: WIN oder LOSS

    Returns:
        dict mit trade_id, outcome, pnl, fee, new_bankroll
    """
    outcome = outcome.upper()
    if outcome not in ["WIN", "LOSS"]:
        raise ValueError("Outcome muss WIN oder LOSS sein")

    trades = read_all_trades()

    # Finde Trade
    trade_found = None
    trade_index = None
    for i, trade in enumerate(trades):
        if trade["id"] == trade_id:
            trade_found = trade
            trade_index = i
            break

    if trade_found is None:
        raise ValueError(f"Trade {trade_id} nicht gefunden")

    if trade_found["status"] == "CLOSED":
        raise ValueError(f"Trade {trade_id} bereits aufgeloest")

    # Werte extrahieren
    stake = float(trade_found["stake"])
    ask_price = float(trade_found["ask_price"])

    # Fee berechnen
    fee = calculate_fee(ask_price)

    # PnL berechnen
    if outcome == "WIN":
        # Gewinn: stake * (1/ask - 1) * (1 - fee)
        gross_profit = stake * (1 / ask_price - 1)
        pnl = gross_profit * (1 - fee)
    else:
        # Verlust: -stake
        pnl = -stake

    # Trade updaten
    trades[trade_index]["status"] = "CLOSED"
    trades[trade_index]["outcome"] = outcome
    trades[trade_index]["pnl"] = f"{pnl:.2f}"
    trades[trade_index]["fee"] = f"{fee:.4f}"

    write_all_trades(trades)

    # Neuen Bankroll berechnen
    new_bankroll = get_current_bankroll()

    print(f"\nTrade {trade_id} aufgeloest:")
    print(f"  Outcome: {outcome}")
    print(f"  Fee: {fee:.2%}")
    print(f"  PnL: ${pnl:+.2f}")
    print(f"  Neuer Bankroll: ${new_bankroll:.2f}")

    return {
        "trade_id": trade_id,
        "outcome": outcome,
        "pnl": pnl,
        "fee": fee,
        "new_bankroll": new_bankroll
    }


def daily_summary(date: str = None) -> dict:
    """
    Tagesuebersicht anzeigen

    Args:
        date: Datum im Format YYYY-MM-DD (default: heute)

    Returns:
        dict mit Statistiken
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    trades = read_all_trades()

    # Filtere nach Datum
    day_trades = [t for t in trades if t["timestamp"].startswith(date)]
    closed_trades = [t for t in day_trades if t["status"] == "CLOSED"]

    # Statistiken berechnen
    total_trades = len(day_trades)
    closed_count = len(closed_trades)
    wins = len([t for t in closed_trades if t["outcome"] == "WIN"])
    losses = len([t for t in closed_trades if t["outcome"] == "LOSS"])

    win_rate = wins / closed_count if closed_count > 0 else 0.0

    total_pnl = sum(float(t["pnl"]) for t in closed_trades if t["pnl"])

    # Aktueller Bankroll (alle Trades, nicht nur heute)
    current_bankroll = get_current_bankroll()

    # Daily Loss Check
    daily_loss = -total_pnl if total_pnl < 0 else 0
    daily_loss_percent = daily_loss / STARTING_CAPITAL
    daily_loss_stop = daily_loss_percent >= MAX_DAILY_LOSS_PERCENT

    # Ausgabe
    print("\n" + "=" * 50)
    print(f"DAILY SUMMARY - {date}")
    print("=" * 50)
    print(f"  Total Trades:    {total_trades}")
    print(f"  Closed:          {closed_count}")
    print(f"  Open:            {total_trades - closed_count}")
    print("-" * 50)
    print(f"  Wins:            {wins}")
    print(f"  Losses:          {losses}")
    print(f"  Win Rate:        {win_rate:.1%}")
    print("-" * 50)
    print(f"  Total PnL:       ${total_pnl:+.2f}")
    print(f"  Daily Loss:      ${daily_loss:.2f} ({daily_loss_percent:.1%})")
    print("-" * 50)
    print(f"  Bankroll:        ${current_bankroll:.2f}")
    print(f"  Starting:        ${STARTING_CAPITAL:.2f}")
    print(f"  All-Time PnL:    ${current_bankroll - STARTING_CAPITAL:+.2f}")
    print("-" * 50)

    if daily_loss_stop:
        print("  >>> DAILY LOSS STOP ERREICHT! <<<")
    else:
        remaining = (MAX_DAILY_LOSS_PERCENT * STARTING_CAPITAL) - daily_loss
        print(f"  Daily Loss verbleibend: ${remaining:.2f}")

    print("=" * 50)

    return {
        "date": date,
        "total_trades": total_trades,
        "closed": closed_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "daily_loss": daily_loss,
        "daily_loss_percent": daily_loss_percent,
        "daily_loss_stop": daily_loss_stop,
        "current_bankroll": current_bankroll
    }


def show_open_trades():
    """Zeige alle offenen Trades"""
    trades = read_all_trades()
    open_trades = [t for t in trades if t["status"] == "OPEN"]

    if not open_trades:
        print("\nKeine offenen Trades.")
        return []

    print("\n" + "=" * 60)
    print("OFFENE TRADES")
    print("=" * 60)
    print(f"{'ID':<6} {'Zeit':<20} {'Dir':<5} {'Stake':<8} {'Ask':<8} {'EV':<8}")
    print("-" * 60)

    for t in open_trades:
        print(f"{t['id']:<6} {t['timestamp']:<20} {t['direction']:<5} "
              f"${float(t['stake']):<7.2f} {float(t['ask_price']):<8.4f} "
              f"{float(t['ev']):.2%}")

    print("=" * 60)
    return open_trades


def main():
    """Demo / CLI Interface"""
    import sys

    if len(sys.argv) < 2:
        print("Trade Journal - Verwendung:")
        print("  python trade_journal.py log <direction> <stake> <ask> <p_win> <ev>")
        print("  python trade_journal.py resolve <trade_id> <WIN|LOSS>")
        print("  python trade_journal.py summary [date]")
        print("  python trade_journal.py open")
        print("  python trade_journal.py demo")
        return

    command = sys.argv[1].lower()

    if command == "log":
        if len(sys.argv) < 7:
            print("Fehler: log braucht direction, stake, ask, p_win, ev")
            return
        direction = sys.argv[2]
        stake = float(sys.argv[3])
        ask = float(sys.argv[4])
        p_win = float(sys.argv[5])
        ev = float(sys.argv[6])
        log_trade(direction, stake, ask, p_win, ev)

    elif command == "resolve":
        if len(sys.argv) < 4:
            print("Fehler: resolve braucht trade_id und outcome")
            return
        trade_id = sys.argv[2].upper()
        outcome = sys.argv[3].upper()
        resolve_trade(trade_id, outcome)

    elif command == "summary":
        date = sys.argv[2] if len(sys.argv) > 2 else None
        daily_summary(date)

    elif command == "open":
        show_open_trades()

    elif command == "demo":
        print("=== DEMO: Trade Journal ===\n")

        # Trade 1: WIN
        print("1. Trade eintragen (UP, $3, ask=0.45)")
        t1 = log_trade("UP", 3.00, 0.45, 0.52, 0.035)

        # Trade 2: LOSS
        print("\n2. Trade eintragen (DOWN, $2.91, ask=0.55)")
        t2 = log_trade("DOWN", 2.91, 0.55, 0.48, 0.032)

        # Offene Trades zeigen
        print("\n3. Offene Trades:")
        show_open_trades()

        # Trade 1 aufloesen: WIN
        print("\n4. Trade 1 aufloesen: WIN")
        resolve_trade(t1, "WIN")

        # Trade 2 aufloesen: LOSS
        print("\n5. Trade 2 aufloesen: LOSS")
        resolve_trade(t2, "LOSS")

        # Summary
        print("\n6. Tagesuebersicht:")
        daily_summary()

    else:
        print(f"Unbekannter Befehl: {command}")


if __name__ == "__main__":
    main()
