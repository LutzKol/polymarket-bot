# Chainlink Oracle Lag Analysis Report

## ECHTE DATEN - Keine Simulation!

Analyse basiert auf echten Chainlink BTC/USD Oracle-Daten von der Polygon Blockchain.

## Summary

| Metric | Value |
|--------|-------|
| Total Oracle Updates | 1,003 |
| Significant Price Moves (>=0.35%) | 392 |
| Signal Rate | 39.08% |
| Mean Price Change | 0.789% |
| Max Price Change | 3.586% |
| Upward Signals | 190 |
| Downward Signals | 202 |
| Avg Interval (sig. moves) | 2472s |
| Oracle Updates/Day | 33.5 |
| Trading Signals/Day | 13.1 |
| Price Range | $61,163.50 - $90,742.77 |

## Interpretation

Wenn der Oracle-Preis um X% zwischen Updates springt, war der Spot-Preis
**mindestens X%** vor dem Oracle. Das ist unser Trading-Fenster.

## Significant Moves by Day

| Date | Events |
|------|--------|
| 2026-01-22 | 5 |
| 2026-01-23 | 6 |
| 2026-01-25 | 5 |
| 2026-01-26 | 9 |
| 2026-01-27 | 8 |
| 2026-01-28 | 6 |
| 2026-01-29 | 8 |
| 2026-01-30 | 14 |
| 2026-01-31 | 7 |
| 2026-02-01 | 15 |
| 2026-02-02 | 18 |
| 2026-02-03 | 18 |
| 2026-02-04 | 20 |
| 2026-02-05 | 36 |
| 2026-02-06 | 31 |
| 2026-02-07 | 19 |
| 2026-02-08 | 13 |
| 2026-02-09 | 19 |
| 2026-02-10 | 13 |
| 2026-02-11 | 18 |
| 2026-02-12 | 19 |
| 2026-02-13 | 10 |
| 2026-02-14 | 10 |
| 2026-02-15 | 11 |
| 2026-02-16 | 9 |
| 2026-02-17 | 13 |
| 2026-02-18 | 11 |
| 2026-02-19 | 8 |
| 2026-02-20 | 12 |
| 2026-02-21 | 1 |

## Significant Moves by Hour (UTC)

| Hour | Events |
|------|--------|
| 00:00 | 13 |
| 01:00 | 13 |
| 02:00 | 14 |
| 03:00 | 16 |
| 04:00 | 16 |
| 05:00 | 9 |
| 06:00 | 14 |
| 07:00 | 11 |
| 08:00 | 16 |
| 09:00 | 14 |
| 10:00 | 12 |
| 11:00 | 13 |
| 12:00 | 11 |
| 13:00 | 13 |
| 14:00 | 20 |
| 15:00 | 29 |
| 16:00 | 22 |
| 17:00 | 22 |
| 18:00 | 28 |
| 19:00 | 23 |
| 20:00 | 18 |
| 21:00 | 18 |
| 22:00 | 11 |
| 23:00 | 16 |

## Fazit

**Ist der Edge real und häufig genug?**

**JA** - Die ECHTE Analyse zeigt einen viablen Edge:

- **39.08%** der Oracle-Updates zeigen Preisänderungen >= 0.35%
- Die durchschnittliche Preisänderung von **0.789%** ist signifikant
- **13.1** Trading-Signale pro Tag
- Die Balance zwischen Up/Down Signalen (190/202) zeigt keine systematische Verzerrung

**Empfehlung:** Weiter mit Phase 3 (Feature Engineering & Modell)

---
*Generiert: 2026-02-21 11:01 UTC*
*Threshold: 0.35%*
*Datenquelle: ECHTE Chainlink Oracle Daten (Polygon RPC)*
