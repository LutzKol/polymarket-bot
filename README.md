# Polymarket Bot

Kollaboratives Projekt zur Entwicklung eines ML-basierten Trading-Bots für Polymarket BTC-Märkte.

## Projektstruktur

```
polymarket-bot/
├── person-a/          # Person A's Arbeitsbereich
├── person-b/          # Person B's Arbeitsbereich
│   ├── *.py           # Python Scripts
│   ├── *.csv          # Daten (Chainlink History, Labels)
│   └── docs/          # Dokumentation & Reports
├── shared/            # Gemeinsamer Code (später)
└── README.md
```

---

## Phase 1 — Oracle Lag Monitor

**Chainlink BTC/USD (Polygon Mainnet) vs. Binance Spot**

### Was macht dieses Script?

Dieses Script überwacht in Echtzeit den **Lag** zwischen dem Chainlink BTC/USD Oracle auf Polygon und dem aktuellen Binance Spot-Preis.

- Wenn der Lag größer als **±0.35%** ist → gibt es einen ALERT im Terminal
- Alle Daten werden in eine **CSV-Datei** geloggt für spätere Analyse
- Das ist die **Daten-Grundlage** für unsere Trading-Strategie

---

## Setup

### Schritt 1 — Alchemy RPC URL holen

1. Gehe zu [alchemy.com](https://alchemy.com) und logge dich ein
2. Klicke auf **"Create new app"**
3. **Wichtig beim Network:** Wähle **"Polygon Mainnet"** (NICHT "Polygon zkEVM Mainnet"!)
4. App erstellen → dann auf die App klicken → **"API Key"** kopieren
5. Deine RPC URL sieht dann so aus:
   ```
   https://polygon-mainnet.g.alchemy.com/v2/DEIN_KEY_HIER
   ```

### Schritt 2 — config.json ausfüllen

Öffne die Datei `config.json` und ersetze den Platzhalter mit deiner URL:

```json
{
    "polygon_rpc_url": "https://polygon-mainnet.g.alchemy.com/v2/DEIN_KEY_HIER",
    "alert_threshold_pct": 0.35,
    "oracle_poll_seconds": 5,
    "log_file": "oracle_lag_log.csv"
}
```

### Schritt 3 — Dependencies installieren

```bash
pip install -r requirements.txt
```

---

## Script starten

```bash
python oracle_monitor.py
```

**Stoppen:** `CTRL + C`

---

## Wichtige Technische Details

| Parameter | Wert |
|---|---|
| Chainlink Adresse | `0xc907E116054Ad103354f2D350FD2514433D57F6f` |
| Netzwerk | Polygon Mainnet (PoS) |
| Dezimalstellen | 8 (Chainlink Standard für BTC/USD) |
| Oracle Trigger | ±0.5% Preisabweichung ODER alle 3600s |
| Binance Feed | `wss://stream.binance.com:9443/ws/btcusdt@ticker` |
| Alert-Schwelle | 0.35% (70% der Oracle-Trigger-Schwelle) |

---

## Aktueller Stand

### Daten
- **chainlink_history.csv**: Chainlink Oracle Updates (BTC/USD)
- **labeled_data.csv**: Gelabelte Daten für ML (Up=1, Down=0)

### Modell (Person B)
- Logistische Regression mit L2-Regularisierung
- Features: `oracle_lag_pct`, `sigma`, `momentum`
- Walk-Forward Backtest
- Ergebnis: Brier Score ~0.25 (Baseline-Level)

### Dokumentation
- `docs/model_report.md` - Modell-Evaluation
- `docs/edge_hypothesis.md` - Trading-Hypothese
- `docs/CRITICAL_RULES.md` - Projekt-Regeln
