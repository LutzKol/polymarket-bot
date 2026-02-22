# Risk Parameters

## Standard-Parameter

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| Fee | 0-1.56% | Variable Taker Fee (siehe Gebuehrenstruktur) |
| Slippage | 0.5% | Ausfuehrungsabweichung |
| Min EV | +3.0% | Minimaler erwarteter Wert |

---

## Gebuehrenstruktur

### BTC 5-Min Crypto Markets

| Typ | Fee | Beschreibung |
|-----|-----|--------------|
| Maker Fee | 0% | Orders die Liquiditaet hinzufuegen |
| Taker Fee | 0-1.56% | Orders die Liquiditaet entfernen |
| Maker Rebate | 20% | Anteil an gesammelten Taker Fees |

**Wichtig:** Die meisten Market-Takes (sofortige Ausfuehrung) sind Taker-Orders und unterliegen der variablen Fee.

### Fee-Formel

```
fee = contracts × 0.25 × (p × (1 - p))^2
```

Wobei `p` der Ausfuehrungspreis ist.

**Effektive Fee nach Preis:**

| Preis | Fee    | vs. alte Annahme (2%) |
|-------|--------|----------------------|
| 0.50  | 1.56%  | -0.44%               |
| 0.45  | 1.53%  | -0.47%               |
| 0.40  | 1.44%  | -0.56%               |
| 0.35  | 1.29%  | -0.71%               |
| 0.30  | 1.10%  | -0.90%               |
| 0.25  | 0.88%  | -1.12%               |
| 0.20  | 0.64%  | -1.36%               |

**Erkenntnis:** Die Fee ist maximal bei p=0.50 und nimmt zu den Extremen (0 und 1) ab.

### Weitere Kosten

| Kostenart | Betrag | Anmerkung |
|-----------|--------|-----------|
| Deposit | 0% | Polymarket selbst |
| Withdrawal | 0% | Polymarket selbst |
| Gas | ~$0.01 | Polygon L2, minimal |
| Bridging | variabel | Third-Party Dienste |

### Welche Maerkte haben Fees?

- ✓ 5-min Crypto Markets (betrifft uns)
- ✓ 15-min Crypto Markets
- ✓ NCAAB (ab 18.02.2026)
- ✓ Serie A (ab 18.02.2026)
- ✗ Alle anderen Maerkte: 0% Fee

**Quellen:**
- https://docs.polymarket.com/polymarket-learn/trading/fees
- https://quantjourney.substack.com/p/understanding-the-polymarket-fee

---

## Break-Even Tabelle

Die Break-Even Wahrscheinlichkeit gibt an, ab welcher tatsaechlichen Wahrscheinlichkeit ein Trade profitabel wird.

**Formel (mit variabler Fee):**
```
fee(p) = 0.25 × (p × (1-p))^2
breakeven_p = ask_price × (1 + slippage) / (1 - fee(ask_price))
```

| Ask-Preis | Fee    | Break-Even % | Alt (2% Fee) | Status |
|-----------|--------|--------------|--------------|--------|
| 0.50      | 1.56%  | 51.05%       | 51.3%        | OK |
| 0.52      | 1.54%  | 53.10%       | 53.3%        | OK |
| 0.55      | 1.48%  | 56.09%       | 56.4%        | CAUTION |
| 0.58      | 1.39%  | 59.02%       | 59.5%        | AVOID |

**Hinweis:** Die niedrigere variable Fee fuehrt zu geringfuegig besseren Break-Even Werten als bei der alten 2%-Annahme.

## Warum Ask > 0.55 vermeiden

### 1. Hohe Break-Even Schwelle

Bei Ask = 0.55 benoetigt man eine tatsaechliche Wahrscheinlichkeit von mindestens 56.1% um break-even zu sein. Das bedeutet:
- Die Marktprognose muss um mindestens 1.1 Prozentpunkte daneben liegen
- Wenig Spielraum fuer Fehler in der eigenen Einschaetzung

### 2. Abnehmender Edge

| Ask | Fee   | Break-Even | Benoetigter Edge |
|-----|-------|------------|------------------|
| 0.50 | 1.56% | 51.05% | +1.05% |
| 0.52 | 1.54% | 53.10% | +1.10% |
| 0.55 | 1.48% | 56.09% | +1.09% |
| 0.58 | 1.39% | 59.02% | +1.02% |

Je hoeher der Ask-Preis, desto groesser muss der eigene Informationsvorsprung sein.

**Hinweis:** Durch die variable Fee-Struktur ist der benoetigte Edge relativ konstant (~1%).

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

1. **Bevorzugt:** Ask <= 0.52 (Break-Even <= 53.1%)
2. **Akzeptabel:** Ask <= 0.55 mit starkem Edge (Break-Even <= 56.1%)
3. **Vermeiden:** Ask > 0.55 (Break-Even > 56.1%)

### Minimum EV Regel

Nur Trades eingehen wenn:
```
eigene_wahrscheinlichkeit >= breakeven_p + min_ev
```

Mit Min EV = 3%:
- Bei Ask = 0.50: Eigene P muss >= 54.05% sein
- Bei Ask = 0.52: Eigene P muss >= 56.10% sein
- Bei Ask = 0.55: Eigene P muss >= 59.09% sein

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
