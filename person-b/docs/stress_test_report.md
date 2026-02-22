# Stress Test Report

## Übersicht

Simulation extremer Verlustszenarien zur Validierung des Risk Management Systems.

| Parameter | Wert |
|-----------|------|
| Startkapital | $100 |
| Stake pro Trade | 3% |
| Max Daily Loss | 8% ($8) |
| Cooldown Trigger | 3 Verluste in Folge |

---

## Szenario A: 5 Verluste in Folge

**Annahme:** 5 aufeinanderfolgende verlorene Trades

### Verlauf

| Trade | Stake | Bankroll | Kum. Verlust | Status |
|-------|-------|----------|--------------|--------|
| 1 | $3.00 | $97.00 | $3.00 (3.0%) | - |
| 2 | $2.91 | $94.09 | $5.91 (5.9%) | - |
| 3 | $2.82 | $91.27 | $8.73 (8.7%) | Cooldown + Daily Stop |
| 4 | - | - | - | BLOCKIERT |
| 5 | - | - | - | BLOCKIERT |

### Ergebnis

| Frage | Antwort |
|-------|---------|
| Cooldown ausgelöst? | JA (nach Trade 3) |
| Daily Loss Stop ausgelöst? | JA (nach Trade 3) |
| Finaler Bankroll | $91.27 |
| Gesamtverlust | $8.73 (8.7%) |

**Fazit:** System stoppt automatisch nach 3 Verlusten. Trades 4-5 werden blockiert.

---

## Szenario B: Max Daily Loss erreicht

**Frage:** Wie viele Trades bis 8% Daily Loss?

### Verlauf

| Trade | Verlust | Kumulativ | Bankroll |
|-------|---------|-----------|----------|
| 1 | $3.00 | $3.00 | $97.00 |
| 2 | $2.91 | $5.91 | $94.09 |
| 3 | $2.82 | $8.73 | $91.27 |

**>>> DAILY LOSS STOP nach Trade 3**

### Ergebnis

| Metrik | Wert |
|--------|------|
| Trades bis Stop | 3 |
| Gesamtverlust | $8.73 |
| Verbleibender Bankroll | $91.27 |

**Was passiert danach:** Trading wird für den Rest des Tages gestoppt.

---

## Szenario C: Schlechtester Tag

**Annahme:** 10 Trades, alle verloren (Worst Case)

### Verlauf

| Trade | Verlust | Bankroll | Status |
|-------|---------|----------|--------|
| 1 | $3.00 | $97.00 | Ausgeführt |
| 2 | $2.91 | $94.09 | Ausgeführt |
| 3 | $2.82 | $91.27 | Ausgeführt + STOP |
| 4-10 | - | - | BLOCKIERT |

### Ergebnis

| Metrik | Wert |
|--------|------|
| Trades ausgeführt | 3 |
| Trades blockiert | 7 |
| Finaler Bankroll | $91.27 |
| Gesamtverlust | $8.73 (8.7%) |

### Vergleich: Mit vs. Ohne Daily Loss Stop

| Szenario | Bankroll | Verlust |
|----------|----------|---------|
| MIT Daily Loss Stop | $91.27 | $8.73 (8.7%) |
| OHNE Daily Loss Stop | $73.74 | $26.26 (26.3%) |
| **Ersparnis** | - | **$17.52** |

---

## Gesamtfazit

### Überlebt das System extreme Verlustphasen?

## JA

### Begründung

1. **Daily Loss Stop (8%)** schützt vor Tagesverlusten > $8
2. **Cooldown nach 3 Verlusten** verhindert Tilt-Trading
3. **Kleine Stakes (3%)** limitieren Einzelverluste
4. **Worst Case pro Tag:** Max ~8.7% Verlust (nicht 100%)
5. **Drawdown-Resistenz:** System braucht 3 aufeinanderfolgende Worst-Case-Tage für 25% Drawdown

### Recovery-Analyse

| Verlust | Benötigt für Break-Even | Tage bei +3% täglich |
|---------|-------------------------|----------------------|
| 8.7% (1 Tag) | +9.5% | ~3 Tage |
| 17% (2 Tage) | +20.5% | ~7 Tage |
| 25% (3 Tage) | +33.3% | ~11 Tage |

### Schlussfolgerung

Das Risk Management System ist robust gegen extreme Verlustphasen:

- **Kapitalschutz:** Maximal ~9% Verlust pro Tag möglich
- **Psychologischer Schutz:** Cooldown verhindert emotionale Entscheidungen
- **Skalierte Stakes:** Prozentuale Stakes reduzieren absoluten Verlust bei fallendem Bankroll
- **Recovery möglich:** Selbst nach 3 Worst-Case-Tagen ist Recovery realistisch

**Status: SYSTEM VALIDIERT**
