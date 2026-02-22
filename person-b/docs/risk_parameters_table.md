# Risk Parameters - Vollständige Dokumentation

## Kontext

| Parameter | Wert |
|-----------|------|
| Startkapital | $100 |
| Min Bet Polymarket | $1 |
| Fee | 0-1.56% (variabel) |
| Slippage | 0.5% |

---

## Übersichtstabelle

| Parameter | Wert | Hart/Weich | Kurzbegründung |
|-----------|------|------------|----------------|
| Max Stake pro Trade | 3% ($3) | Hart | Kelly-Kriterium konservativ |
| Min EV Schwelle | +3% | Hart | Deckung von Varianz |
| Max Daily Loss | 8% ($8) | Hart | Ruin-Vermeidung |
| Max Trades pro Tag | 10 | Weich | Qualität > Quantität |
| Cooldown nach Verlusten | 3 Verluste = 30 Min | Hart | Tilt-Vermeidung |
| Min Ask-Preis | 0.40 | Weich | Ausreichend Upside |
| Max Ask-Preis | 0.60 | Weich | Risiko-Reward Verhältnis |
| Brier Score Limit | < 0.24 | Hart | Signifikant besser als Zufall |
| Min Win Rate (Paper) | > 54% auf 200 Trades | Hart | Statistische Signifikanz |
| Startkapital Live | 25% ($25) erste Woche | Weich | Graduelle Skalierung |

---

## Detaillierte Begründungen

### 1. Max Stake pro Trade (3% = $3)

**Typ:** Hart

**Mathematische Begründung:**
Kelly-Kriterium empfiehlt optimale Einsatzgröße: `f = (p*b - q) / b`
- p = Gewinnwahrscheinlichkeit
- q = Verlustwahrscheinlichkeit (1-p)
- b = Gewinn-Verlust-Verhältnis

Konservative Anwendung: 25-50% des Kelly-Wertes = typisch 2-5% pro Trade.

**Beispielrechnung bei Verletzung:**
Bei 10% Stake und 5 aufeinanderfolgenden Verlusten:
```
$100 × 0.90^5 = $59.05 (-41%)
```
Um von $59 auf $100 zurückzukommen: +69% nötig!

**Warum Hart:**
Ruinwahrscheinlichkeit steigt exponentiell mit Einsatzgröße. Nicht verhandelbar.

---

### 2. Min EV Schwelle (+3%)

**Typ:** Hart

**Mathematische Begründung:**
EV muss abdecken:
- Fee: ~1%
- Slippage: ~0.5%
- Varianz-Puffer: ~1.5%

Mindestens +3% EV, um profitabel zu sein.

**Beispielrechnung bei Verletzung:**
Bei +1% EV nach 100 Trades à $3:
```
Erwarteter Gewinn: 100 × $3 × 0.01 = $3
Standardabweichung: ~$15 (bei 50% Win Rate)
```
Hohe Wahrscheinlichkeit für negativen Outcome trotz positivem EV.

**Warum Hart:**
Ohne ausreichenden Edge kein nachhaltiger Gewinn möglich.

---

### 3. Max Daily Loss (8% = $8)

**Typ:** Hart

**Mathematische Begründung:**
Begrenzung des Drawdowns auf psychologisch und mathematisch erholbare Level.

Recovery-Tabelle:
| Verlust | Benötigter Gewinn für Break-Even |
|---------|----------------------------------|
| 8% | +8.7% |
| 15% | +17.6% |
| 20% | +25.0% |
| 30% | +42.9% |

**Beispielrechnung bei Verletzung:**
Bei 20% Daily Loss:
```
$100 → $80
Um zurück auf $100: $80 × 1.25 = $100 (+25% nötig)
```

**Warum Hart:**
Kombinierter psychologischer und mathematischer Schutz. Bei Erreichen: Trading für den Tag beenden.

---

### 4. Max Trades pro Tag (10)

**Typ:** Weich

**Mathematische Begründung:**
- Fokus auf die besten Opportunities
- Vermeidung von "Action Bias"
- Qualität vor Quantität

Bei 10 Trades mit +3% EV besser als 20 Trades mit +1.5% durchschnittlichem EV.

**Beispielrechnung bei Verletzung:**
Mehr Trades = schlechtere durchschnittliche EV:
```
10 beste Trades: Ø +4% EV
20 Trades (inkl. mittelmäßige): Ø +2.5% EV
```

**Warum Weich:**
Kann bei nachgewiesener Edge und konstant guten Opportunities erhöht werden.

---

### 5. Cooldown nach Verlusten (3 Verluste = 30 Min)

**Typ:** Hart

**Mathematische Begründung:**
Verhindert Tilt-Trading und emotionale Entscheidungen.

Psychologische Studien zeigen:
- Nach 3+ Verlusten steigt Risikobereitschaft
- Rationale Entscheidungsfähigkeit sinkt
- "Revenge Trading" führt zu größeren Verlusten

**Beispielrechnung bei Verletzung:**
Typisches Tilt-Szenario:
```
3 Verluste: -$9
Tilt-Trade mit 10% Stake: -$10
Gesamtverlust: -$19 statt -$9
```

**Warum Hart:**
Menschlicher Faktor nicht verhandelbar. Emotionen überschreiben Logik.

---

### 6. Min Ask-Preis (0.40)

**Typ:** Weich

**Mathematische Begründung:**
- Unter 0.40: Oft geringe Liquidität
- Höheres Slippage-Risiko
- Schwieriger Exit bei ungünstiger Entwicklung

**Beispielrechnung bei Verletzung:**
Bei Ask 0.25:
```
Kauf: 0.25 + 1% Slippage = 0.253
Versuch zu verkaufen bei 0.20: Spread oft 5-10%
Effektiver Verlust: 0.253 → 0.18 = -29%
```

**Warum Weich:**
Kann bei guter Liquidität (hohes Volumen, enger Spread) angepasst werden.

---

### 7. Max Ask-Preis (0.60)

**Typ:** Weich

**Mathematische Begründung:**
Risk-Reward wird ungünstig über 0.60:
- Max Gewinn = 1.00 - Ask
- Max Verlust = Ask

Bei 0.60: Max Gewinn 40c, Max Verlust 60c (Ratio 0.67)
Bei 0.70: Max Gewinn 30c, Max Verlust 70c (Ratio 0.43)

**Beispielrechnung bei Verletzung:**
Bei Ask 0.70 und 50% Win Rate:
```
Erwartung = 0.5 × $0.30 - 0.5 × $0.70 = -$0.20 pro Dollar
```
Braucht >70% Win Rate für Break-Even!

**Warum Weich:**
Kann bei sehr hohem, nachgewiesenem Edge überschritten werden.

---

### 8. Brier Score Limit (< 0.24)

**Typ:** Hart

**Mathematische Begründung:**
Brier Score misst Vorhersagequalität:
- 0.00 = Perfekt
- 0.25 = Zufall (Münzwurf)
- 0.50 = Immer falsch

Formel: `BS = (1/n) × Σ(forecast - outcome)²`

**Beispielrechnung bei Verletzung:**
Bei Brier Score 0.26:
```
Schlechter als reiner Münzwurf
Jede Prognose vernichtet Kapital
```

**Warum Hart:**
Objektives, mathematisches Maß für Prognosequalität. Nicht verhandelbar.

---

### 9. Min Win Rate (> 54% auf 200 Trades)

**Typ:** Hart

**Mathematische Begründung:**
Statistische Signifikanz erfordert ausreichende Stichprobengröße.

Bei angenommener 50% Baseline:
```
200 Trades mit 54% Win Rate:
Z-Score = (0.54 - 0.50) / sqrt(0.25/200) = 1.13
p-Wert ≈ 0.13 (noch nicht signifikant)

Aber: Kombiniert mit EV-Analyse und Brier Score = ausreichend
```

**Beispielrechnung bei Verletzung:**
Bei 50% Win Rate nach 200 Trades:
```
Kein nachweisbarer Edge
Alle Gewinne waren Zufall
Weiteres Trading = Gambling
```

**Warum Hart:**
Statistische Mindestanforderung bevor Live-Trading beginnt.

---

### 10. Startkapital Live (25% = $25)

**Typ:** Weich

**Mathematische Begründung:**
Graduelle Skalierung minimiert Anfängerfehler:
- Woche 1: $25 (25%)
- Woche 2: $50 (50%) bei Erfolg
- Woche 3: $75 (75%) bei Erfolg
- Woche 4: $100 (100%) bei Erfolg

**Beispielrechnung bei Verletzung:**
Volles Kapital sofort bei Systemfehler:
```
Bug in Betting-Logik: 10 Trades à $10 statt $3
Worst Case: -$100 (Totalverlust)

Mit 25% Start:
Worst Case: -$25 (lernt teuer, aber überlebt)
```

**Warum Weich:**
Kann bei stabiler Performance und technischer Validierung beschleunigt werden.

---

## Zusammenfassung

### Harte Regeln (NIEMALS brechen)
1. Max Stake: 3%
2. Min EV: +3%
3. Max Daily Loss: 8%
4. Cooldown: 3 Verluste = 30 Min
5. Brier Score: < 0.24
6. Min Win Rate: > 54% @ 200 Trades

### Weiche Regeln (Mit Begründung anpassbar)
1. Max Trades/Tag: 10
2. Min Ask: 0.40
3. Max Ask: 0.60
4. Startkapital: 25%
