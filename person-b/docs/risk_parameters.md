# Risk Parameters

## Standard-Parameter

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| Fee | 2.0% | Transaktionsgebuehr |
| Slippage | 0.5% | Ausfuehrungsabweichung |
| Min EV | +3.0% | Minimaler erwarteter Wert |

## Break-Even Tabelle

Die Break-Even Wahrscheinlichkeit gibt an, ab welcher tatsaechlichen Wahrscheinlichkeit ein Trade profitabel wird.

**Formel:**
```
breakeven_p = ask_price * (1 + slippage) / (1 - fee)
```

| Ask-Preis | Break-Even % | Status |
|-----------|--------------|--------|
| 0.50 | 51.3% | OK |
| 0.52 | 53.3% | OK |
| 0.55 | 56.4% | CAUTION |
| 0.58 | 59.5% | AVOID |

## Warum Ask > 0.55 vermeiden

### 1. Hohe Break-Even Schwelle

Bei Ask = 0.55 benoetigt man eine tatsaechliche Wahrscheinlichkeit von mindestens 56.4% um break-even zu sein. Das bedeutet:
- Die Marktprognose muss um mindestens 1.4 Prozentpunkte daneben liegen
- Wenig Spielraum fuer Fehler in der eigenen Einschaetzung

### 2. Abnehmender Edge

| Ask | Break-Even | Benoetigter Edge |
|-----|------------|------------------|
| 0.50 | 51.3% | +1.3% |
| 0.52 | 53.3% | +1.3% |
| 0.55 | 56.4% | +1.4% |
| 0.58 | 59.5% | +1.5% |

Je hoeher der Ask-Preis, desto groesser muss der eigene Informationsvorsprung sein.

### 3. Risiko-Reward Verhaeltnis

Bei hohen Ask-Preisen:
- Geringerer potenzieller Gewinn (max 1.00 - ask)
- Hoeherer potenzieller Verlust (ask)
- Schlechteres Risiko-Reward Verhaeltnis

**Beispiel bei Ask = 0.58:**
- Maximaler Gewinn: 0.42 (42 Cent pro Kontrakt)
- Maximaler Verlust: 0.58 (58 Cent pro Kontrakt)
- Ratio: 0.72:1 (ungünstig)

**Beispiel bei Ask = 0.50:**
- Maximaler Gewinn: 0.50 (50 Cent pro Kontrakt)
- Maximaler Verlust: 0.50 (50 Cent pro Kontrakt)
- Ratio: 1:1 (neutral)

## Empfehlung

1. **Bevorzugt:** Ask <= 0.52 (Break-Even <= 53.3%)
2. **Akzeptabel:** Ask <= 0.55 mit starkem Edge (Break-Even <= 56.4%)
3. **Vermeiden:** Ask > 0.55 (Break-Even > 56.4%)

### Minimum EV Regel

Nur Trades eingehen wenn:
```
eigene_wahrscheinlichkeit >= breakeven_p + min_ev
```

Mit Min EV = 3%:
- Bei Ask = 0.50: Eigene P muss >= 54.3% sein
- Bei Ask = 0.52: Eigene P muss >= 56.3% sein
- Bei Ask = 0.55: Eigene P muss >= 59.4% sein

## Slippage-Analyse (aus Live-Daten)

Gemessen am: 2026-02-22
Anzahl Maerkte: 5

### Orderbook-Struktur

BTC 5-Min Maerkte zeigen typischerweise:
- **Orderbook-Tiefe:** 40,000-60,000 Kontrakte
- **Preisniveaus:** 40-50 Levels
- **Spread:** Variiert stark je nach Marktphase

### Slippage nach Ordergroesse

| Ordergroesse | Durchschn. Slippage | Max Slippage |
|--------------|---------------------|--------------|
| $10          | ~0.15%              | ~0.25%       |
| $25          | ~0.50%              | ~0.70%       |
| $50          | ~1.20%              | ~1.50%       |

**Hinweis:** Bei extremen Preisen (>0.90 oder <0.10) ist Slippage oft 0%,
da alle Liquiditaet auf einem Preisniveau konzentriert ist. Die obigen
Werte gelten fuer balancierte Maerkte (Ask zwischen 0.40-0.60).

### Empfehlung: Maximale Ordergroesse

Um Slippage < 0.5% zu halten:
- **Empfohlen:** $10-$20 pro Trade
- **Maximum:** $25 pro Trade
- **Vermeiden:** > $50 (Slippage > 1%)

### Begruendung

1. BTC 5-Min Maerkte haben begrenzte Liquiditaet
2. Orderbook-Tiefe variiert stark je nach Marktphase
3. Groessere Orders fressen durch mehrere Preisniveaus
4. Bei extremen Preisen (nahe 0 oder 1) ist Slippage minimal

### Slippage-Formel

```python
# Fill-Preis Berechnung
total_cost = 0
total_contracts = 0
for price, size in asks:
    contracts_at_level = min(remaining_usd / price, size)
    total_cost += contracts_at_level * price
    total_contracts += contracts_at_level
    remaining_usd -= contracts_at_level * price
fill_price = total_cost / total_contracts

# Slippage in Prozent
slippage = (fill_price - best_ask) / best_ask * 100
```

### Live-Analyse Tool

Slippage kann jederzeit mit dem Script analysiert werden:
```bash
python person-b/slippage_analysis.py
```
