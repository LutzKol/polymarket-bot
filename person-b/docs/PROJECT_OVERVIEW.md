# Polymarket BTC 5-Min Oracle Lag Arbitrage Bot

## Projekt-Zusammenfassung

Algorithmisches Trading System für Polymarket BTC 5-Minuten Up/Down Märkte.

## Team

- **Person A**: Technische Infrastruktur (Entwicklung)
- **Person B**: Strategy Analyst (Analyse, ML, Backtesting, Risk)

## Person B Aufgaben

- Historische Daten analysieren & labeln
- ML Modell trainieren & kalibrieren (scikit-learn, logistische Regression)
- Walk-Forward Backtesting schreiben
- Risk Parameter festlegen & begründen
- Alle Trade-Vorschläge reviewen & journalen
- Wöchentliche Performance-Auswertung

## Kern-Edge: Oracle Lag Arbitrage

Chainlink Oracle Updates auf Polygon kommen **verzögert** im Vergleich zu Binance Spot.

- **Signal-Schwelle**: Lag > 0,35%
- Wenn Lag überschritten wird, wissen wir mit hoher Wahrscheinlichkeit die Richtung

## Projekt-Phasen (6-8 Wochen)

| Phase | Beschreibung | Status |
|-------|--------------|--------|
| 1 | Oracle Lag Monitor | In Arbeit |
| 2 | Multi-Exchange Daten-Pipeline | Ausstehend |
| 3 | Feature Engineering & Modell | Ausstehend |
| 4 | EV Engine & Risikosystem | Ausstehend |
| 5 | Paper Trading Engine | Ausstehend |
| 6 | Live Trading (Human-in-the-Loop) | Ausstehend |

## Technologie-Stack

- Python 3.14
- py-clob-client (Polymarket API)
- scikit-learn (ML)
- python-dotenv (Config)

## API-Endpunkte

- CLOB API: `https://clob.polymarket.com`
- Gamma API: `https://gamma-api.polymarket.com`
- Chainlink Oracle: `https://data.chain.link/streams/btc-usd`

## BTC 5-Min Market Discovery

Die 5-Minuten Märkte folgen einem vorhersagbaren Pattern:

```
Slug: btc-updown-5m-{unix_timestamp}
```

Wobei `unix_timestamp` die **Startzeit** des 5-Minuten Fensters ist.

**Beispiel:**
- Timestamp `1771665300` = 2026-02-21 09:15:00 UTC
- Markt: `btc-updown-5m-1771665300`
- Fenster: 09:15-09:20 UTC
- Resolution: 09:20 UTC

**API-Abruf:**
```python
slug = f"btc-updown-5m-{timestamp}"
resp = httpx.get(f"{GAMMA_API}/events", params={"slug": slug})
```

## Wichtige Dateien

- `.env` — API Credentials (NIEMALS committen!)
- `docs/CRITICAL_RULES.md` — Bindende Regeln
- `test_connection.py` — API Verbindungstest
- `btc_markets.json` — Aktuelle Marktdaten

## Phase 1 Status

- API-Verbindung: OK
- BTC 5-Min Märkte: Abrufbar via Timestamp-Pattern
- Chainlink Oracle: Contract verifiziert auf Polygon

## Phase 2 Status (Analyse)

**Hinweis:** Aktuelle Analyse basiert auf simulierten Daten.
Für Production: Echte Chainlink-Daten mit eigenem RPC-Node oder The Graph API holen.

**Analyseergebnisse (simuliert):**
- Lag Event Rate: 17.95% (bei 0.35% Threshold)
- Mean Lag: 0.570%
- ~12.7 Trading-Signale pro Tag
- Edge erscheint viabel

---

*Projekt-Start: 2026-02-21*
*Phase 1 abgeschlossen: 2026-02-21*
*Phase 2 (Analyse) abgeschlossen: 2026-02-21*
