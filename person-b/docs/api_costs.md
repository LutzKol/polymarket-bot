# API Rate Limits & Costs

## Polymarket APIs

### CLOB API (https://clob.polymarket.com)

| Endpoint | Rate Limit | Beschreibung |
|----------|-----------|--------------|
| General | 9,000 req / 10s | Alle CLOB Endpoints |
| `/book` | 1,500 req / 10s | Orderbook für Token |
| `/price` | 1,500 req / 10s | Preis für Token |
| `/midpoint` | 1,500 req / 10s | Midpoint Preis |
| `/books` (batch) | 500 req / 10s | Mehrere Orderbooks |
| `/prices` (batch) | 500 req / 10s | Mehrere Preise |
| Balance GET | 200 req / 10s | Balance abfragen |
| Balance UPDATE | 50 req / 10s | Balance ändern |

**Trading Endpoints:**
- Burst Limit: 10-Sekunden Spitzen erlaubt
- Sustained Limit: 10-Minuten Durchschnitt

### Gamma API (https://gamma-api.polymarket.com)

| Endpoint | Rate Limit |
|----------|-----------|
| General | 4,000 req / 10s |
| `/events` | 500 req / 10s |
| `/markets` | 300 req / 10s |
| `/events` + `/markets` kombiniert | 900 req / 10s |
| `/comments` | 200 req / 10s |
| `/public-search` | 350 req / 10s |

### Data API (https://data-api.polymarket.com)

| Endpoint | Rate Limit |
|----------|-----------|
| General | 1,000 req / 10s |
| `/trades` | 200 req / 10s |
| `/positions` | 150 req / 10s |

### WebSocket (wss://ws-subscriptions-clob.polymarket.com)

| Parameter | Wert |
|-----------|------|
| Verbindungen pro IP | Nicht dokumentiert (vermutlich 5-10) |
| Subscriptions pro Verbindung | Nicht dokumentiert |
| Ping Interval | 30s empfohlen |
| Auto-Disconnect | Bei fehlendem Heartbeat |

**Wichtig:** WebSocket sendet nur Updates bei Orderbook-Änderungen. Bei geringer Marktaktivität können Minuten ohne Updates vergehen.

---

## Binance APIs

### Futures API (https://fapi.binance.com)

| Endpoint | Rate Limit | Weight |
|----------|-----------|--------|
| `/fapi/v1/fundingRate` | 1200 req/min | 1 |
| `/fapi/v1/ticker/price` | 1200 req/min | 1 |
| `/fapi/v1/klines` | 1200 req/min | 5-10 |
| WebSocket Streams | 5 msg/s pro Verbindung | - |

**IP-basierte Limits:**
- 1200 Request Weight pro Minute
- 10 Orders pro Sekunde
- 100.000 Orders pro Tag

**Kosten:** Kostenlos (kein API Key für Public Endpoints nötig)

### Spot API (https://api.binance.com)

| Endpoint | Rate Limit | Weight |
|----------|-----------|--------|
| `/api/v3/ticker/price` | 1200 req/min | 1 |
| `/api/v3/depth` | 1200 req/min | 5-50 |
| WebSocket | Kostenlos | - |

---

## Unsere Nutzung & Empfehlungen

### Aktueller Verbrauch (realtime_monitor.py)

| API | Frequenz | Requests/10s |
|-----|----------|-------------|
| Polymarket `/book` | 5s Polling × 2 Tokens | 4 |
| Binance `/fundingRate` | 30s Polling | 0.3 |
| Polymarket WebSocket | Dauerverbindung | 0 |
| Gamma `/events` | 1× pro Marktwechsel | ~0.1 |

**Gesamt: ~5 req/10s** — Weit unter allen Limits.

### Empfehlungen

1. **Polymarket CLOB:**
   - Polling max alle 2s pro Token (750 req/10s Puffer)
   - WebSocket bevorzugen wenn aktiver Markt
   - Batch-Endpoints nutzen wenn möglich

2. **Binance:**
   - Funding Rate alle 30s ausreichend (ändert sich nur alle 8h)
   - Für Spot-Preis: WebSocket statt Polling

3. **Kritische Limits:**
   - `/events` Endpoint: Max 50/s → Nicht mehr als 10 Märkte parallel abfragen
   - Trading Endpoints: Sustained Limit beachten bei Hochfrequenz

4. **Best Practices:**
   - Exponential Backoff bei 429 Errors
   - Request Weight tracken (Binance)
   - WebSocket Reconnect mit Delay (1s → 2s → 4s → max 60s)

---

## Kostenzusammenfassung

| API | Kosten |
|-----|--------|
| Polymarket (alle) | **Kostenlos** |
| Binance Public | **Kostenlos** |
| Binance Trading | Maker 0.02%, Taker 0.04% |

**Infrastrukturkosten:**
- Keine API-Key-Kosten
- Keine monatlichen Gebühren
- Nur Trading-Fees bei Orderausführung

---

*Erstellt: 2026-02-21*
*Quellen: docs.polymarket.com, binance-docs.github.io*
