# 🔍 Phase 1 — Oracle Lag Monitor

**Chainlink BTC/USD (Polygon Mainnet) vs. Binance Spot**

---

## Was macht dieses Script?

Dieses Script überwacht in Echtzeit den **Lag** zwischen dem Chainlink BTC/USD Oracle auf Polygon und dem aktuellen Binance Spot-Preis.

- Wenn der Lag größer als **±0.35%** ist → gibt es einen ALERT im Terminal
- Alle Daten werden in eine **CSV-Datei** geloggt für spätere Analyse
- Das ist die **Daten-Grundlage** für unsere Trading-Strategie

---

## Voraussetzungen

- Python 3.9 oder neuer
- Ein Alchemy Account mit einer App auf **Polygon Mainnet** (NICHT zkEVM!)

---

## Setup (einmalig)

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

Öffne ein Terminal im Ordner `phase1_oracle_monitor` und führe aus:

```bash
pip install -r requirements.txt
```

---

## Script starten

```bash
python oracle_monitor.py
```

Das Terminal zeigt dann in Echtzeit:

```
══════════════════════════════════════════════════════════════════
  🔍  ORACLE LAG MONITOR  —  PHASE 1
  Chainlink BTC/USD (Polygon) vs. Binance Spot
  Alert-Schwelle: ±0.35%  |  Oracle-Poll: alle 5s
══════════════════════════════════════════════════════════════════

[Web3] ✓ Polygon Mainnet verbunden  (Block #67,123,456)
[Oracle] ✓ Chainlink BTC/USD erreichbar  ($103,250.00  Round #12345)
[Binance] ✓ Verbunden — Empfange BTC/USDT Preise

[2025-05-01T14:23:01]  Oracle: $103,250.00  Spot: $103,610.50  Lag: +0.3487%  Round #12345  Oracle-Alter: 47s
```

Wenn der Lag die Schwelle überschreitet:

```
═════════════════════════════════════════════════════════════════
  🚨  ALERT  —  LAG 📈 RAUF: +0.4201%
  Schwelle: ±0.35%  |  Spot: $103,784.00  |  Oracle: $103,355.00
  → Oracle wird bald in Richtung 📈 RAUF aktualisieren
═════════════════════════════════════════════════════════════════
```

**Stoppen:** `CTRL + C`

---

## Output — CSV Datei

Alle Ticks werden in `oracle_lag_log.csv` gespeichert:

| Spalte | Bedeutung |
|---|---|
| `timestamp_utc` | Zeitstempel (UTC) |
| `roundId` | Chainlink Round ID |
| `oracle_price_usd` | Chainlink Preis in USD |
| `spot_price_usd` | Binance Spot Preis in USD |
| `lag_abs_usd` | Absoluter Lag in USD |
| `lag_pct` | Lag in Prozent |
| `alert` | `ALERT` oder `ok` |

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

## Häufige Fehler

**"FEHLER: config.json nicht gefunden"**
→ Du musst im richtigen Ordner sein. Navigiere in den Ordner `phase1_oracle_monitor` bevor du das Script startest.

**"Polygon RPC nicht erreichbar"**
→ Deine RPC URL in `config.json` ist falsch. Stelle sicher, dass du den richtigen API Key eingefügt hast und die URL mit `https://polygon-mainnet.g.alchemy.com/v2/` beginnt.

**"Chainlink Oracle nicht erreichbar"**
→ Du verwendest wahrscheinlich eine zkEVM URL statt Polygon Mainnet. Erstelle eine neue Alchemy App auf **Polygon Mainnet**.

---

## Nächste Schritte (Phase 2)

Wenn der Monitor läuft und Daten sammelt, gehen wir zu **Phase 2: Feature Engineering** über — dort berechnen wir aus dem Oracle-Lag die eigentlichen Trading-Signale.
