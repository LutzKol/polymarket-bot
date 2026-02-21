# KRITISCHE REGELN — NIEMALS BRECHEN

Diese Regeln sind absolut bindend. Ein Verstoß kann zu erheblichen finanziellen Verlusten führen.

## Daten & Oracle

- **NIEMALS** Spot-Preis statt Oracle-Preis für Auflösungsberechnungen verwenden
  - Der Polymarket-Markt löst basierend auf dem Chainlink Oracle auf, NICHT auf Binance Spot
  - Oracle-Lag ist unser Edge — aber Resolution basiert auf Oracle

## Risikomanagement

- **NIEMALS** mehr als 2% der Bankroll in einem Trade riskieren
- **NIEMALS** Cooldown nach 3 Verlusten überspringen
  - Nach 3 aufeinanderfolgenden Verlusten: Pflicht-Pause einlegen
- **NIEMALS** Kill-Switch ignorieren
  - Wenn Kill-Switch ausgelöst wird: Sofort alle Trading-Aktivitäten stoppen

## Modell & Backtesting

- **NIEMALS** live gehen ohne 200+ Paper Trades mit Win Rate > 54%
- **NIEMALS** Modell vertrauen mit Brier Score > 0,24
  - Brier Score misst Kalibrierung — >0,24 bedeutet unzuverlässige Wahrscheinlichkeiten
- **NIEMALS** In-Sample Performance als echten Edge präsentieren
  - Nur Out-of-Sample / Walk-Forward Ergebnisse zählen

## Live Trading (Phase 6)

- **NIEMALS** Trade ohne manuelle Bestätigung ausführen
  - Human-in-the-Loop ist Pflicht — kein vollautomatisches Trading

---

*Erstellt: 2026-02-21*
*Projekt: Polymarket BTC 5-Min Oracle Lag Arbitrage Bot*
