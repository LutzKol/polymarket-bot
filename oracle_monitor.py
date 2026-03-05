"""
╔══════════════════════════════════════════════════════════════════╗
║         PHASE 1 — ORACLE LAG MONITOR                           ║
║  Chainlink BTC/USD (Polygon) vs. Binance Spot                  ║
║  Loggt jeden Tick und alertet bei Lag > Schwelle               ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ntplib
import websockets
from web3 import Web3
from web3.exceptions import Web3Exception

# ─── CONFIG LADEN ────────────────────────────────────────────────────────────
try:
    with open("config.json") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("FEHLER: config.json nicht gefunden! Bitte im gleichen Ordner ablegen.")
    sys.exit(1)

RPC_URL           = CONFIG["polygon_rpc_url"]
ALERT_THRESHOLD   = CONFIG["alert_threshold_pct"]   # Standard: 0.35%
POLL_INTERVAL     = CONFIG["oracle_poll_seconds"]    # Standard: 5 Sekunden
LOG_FILE          = CONFIG["log_file"]               # Standard: oracle_lag_log.csv

# ─── TERMINAL FARBEN ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ─── CHAINLINK CONTRACT (Polygon Mainnet) ────────────────────────────────────
# BTC/USD Aggregator — offizielle Adresse von Chainlink Docs
CHAINLINK_ADDRESS = Web3.to_checksum_address(
    CONFIG.get("chainlink_address", "0xc907E116054Ad103354f2D350FD2514433D57F6f")
)
CHAINLINK_DECIMALS = 8  # Chainlink BTC/USD gibt Preis mit 8 Dezimalstellen

# Minimales ABI — nur was wir brauchen
CHAINLINK_ABI = [{
    "inputs": [],
    "name": "latestRoundData",
    "outputs": [
        {"name": "roundId",         "type": "uint80"},
        {"name": "answer",          "type": "int256"},
        {"name": "startedAt",       "type": "uint256"},
        {"name": "updatedAt",       "type": "uint256"},
        {"name": "answeredInRound", "type": "uint80"}
    ],
    "stateMutability": "view",
    "type": "function"
}]

# ─── NTP ZEITSYNCHRONISATION ─────────────────────────────────────────────────
ntp_offset = 0.0  # Sekunden — wird beim Start gemessen

def measure_ntp_offset():
    """Misst den Unterschied zwischen lokaler Uhr und NTP-Server."""
    global ntp_offset
    try:
        client = ntplib.NTPClient()
        response = client.request("pool.ntp.org", version=3)
        ntp_offset = response.offset
        print(f"{GREEN}[NTP] ✓ Zeitsynchronisation gemessen  (Offset: {ntp_offset:+.4f}s){RESET}")
    except Exception as e:
        print(f"{YELLOW}[NTP] Warnung: NTP nicht erreichbar ({e}) — verwende lokale Uhr{RESET}")
        ntp_offset = 0.0

def utc_now_corrected():
    """Gibt den aktuellen UTC-Zeitstempel mit NTP-Korrektur zurück."""
    return datetime.fromtimestamp(time.time() + ntp_offset, tz=timezone.utc)

# ─── GLOBALER STATE ──────────────────────────────────────────────────────────
# Beide Coroutines (Oracle + Binance) schreiben hier rein
state = {
    "spot_price":     None,   # Binance BTC/USDT aktueller Preis
    "oracle_price":   None,   # Chainlink letzter bestätigter Preis
    "oracle_round":   None,   # RoundId des letzten Oracle Updates
    "oracle_updated": None,   # Unix Timestamp des letzten Updates
    "start_time":     None,   # Startzeit für Uptime-Berechnung
    "total_ticks":    0,      # Anzahl geloggter Ticks
}

# ─── CSV LOGGER SETUP ────────────────────────────────────────────────────────
log_path = Path(LOG_FILE)
needs_header = not log_path.exists()
csv_file = open(log_path, "a", newline="", encoding="utf-8")
csv_writer = csv.writer(csv_file)

if needs_header:
    csv_writer.writerow([
        "timestamp_utc",
        "roundId",
        "oracle_price_usd",
        "spot_price_usd",
        "lag_abs_usd",
        "lag_pct",
        "alert"
    ])
    csv_file.flush()

# ─── WEB3 + CHAINLINK SETUP ──────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(RPC_URL))
chainlink_contract = w3.eth.contract(address=CHAINLINK_ADDRESS, abi=CHAINLINK_ABI)


# ─── ORACLE ABFRAGE ──────────────────────────────────────────────────────────
def fetch_oracle_data():
    """
    Ruft latestRoundData() vom Chainlink BTC/USD Aggregator ab.
    Gibt (roundId, preis_in_usd, updated_timestamp) zurück.
    Bei Fehler: (None, None, None)
    """
    try:
        raw = chainlink_contract.functions.latestRoundData().call()
        round_id    = raw[0]
        price_usd   = raw[1] / (10 ** CHAINLINK_DECIMALS)
        updated_at  = raw[3]  # Unix timestamp der letzten Oracle-Aktualisierung
        return round_id, price_usd, updated_at
    except (TimeoutError, ConnectionError, OSError) as e:
        print(f"{YELLOW}[Oracle] Netzwerk-Timeout: {e} — versuche es erneut...{RESET}")
        return None, None, None
    except Web3Exception as e:
        print(f"{RED}[Oracle FEHLER] Web3: {e}{RESET}")
        return None, None, None
    except Exception as e:
        print(f"{RED}[Oracle FEHLER] Unerwartet: {e}{RESET}")
        return None, None, None


# ─── LAG BERECHNUNG ──────────────────────────────────────────────────────────
def calculate_lag(oracle_price, spot_price):
    """
    lag_abs = spot - oracle        (absoluter USD Unterschied)
    lag_pct = lag_abs / oracle * 100  (prozentualer Unterschied)

    Positiver Lag → Spot ist über Oracle → Oracle muss rauf
    Negativer Lag → Spot ist unter Oracle → Oracle muss runter
    """
    if oracle_price is None or spot_price is None or oracle_price == 0:
        return None, None
    lag_abs = spot_price - oracle_price
    lag_pct = (lag_abs / oracle_price) * 100
    return lag_abs, lag_pct


# ─── LOGGING + AUSGABE ───────────────────────────────────────────────────────
def log_and_display(round_id, oracle_price, spot_price, lag_abs, lag_pct):
    """CSV loggen und formattierte Konsolenausgabe."""
    ts = utc_now_corrected().strftime("%Y-%m-%dT%H:%M:%S")
    alert = (lag_pct is not None) and (abs(lag_pct) > ALERT_THRESHOLD)
    state["total_ticks"] += 1

    # ── CSV schreiben ──
    csv_writer.writerow([
        ts,
        round_id,
        f"{oracle_price:.2f}" if oracle_price else "",
        f"{spot_price:.2f}"   if spot_price   else "",
        f"{lag_abs:.4f}"      if lag_abs is not None else "",
        f"{lag_pct:.6f}"      if lag_pct is not None else "",
        "ALERT" if alert else "ok"
    ])
    csv_file.flush()

    # ── Terminal ausgabe ──
    lag_color = RED if alert else (YELLOW if lag_pct and abs(lag_pct) > 0.20 else GREEN)
    lag_str   = f"{lag_pct:+.4f}%" if lag_pct is not None else "N/A"
    age_secs  = int(utc_now_corrected().timestamp()) - state["oracle_updated"] if state["oracle_updated"] else 0

    print(
        f"{DIM}[{ts}]{RESET}  "
        f"Oracle: {BOLD}${oracle_price:>10,.2f}{RESET}  "
        f"Spot: {BOLD}${spot_price:>10,.2f}{RESET}  "
        f"Lag: {lag_color}{BOLD}{lag_str:>10}{RESET}  "
        f"{DIM}Round #{round_id}  Oracle-Alter: {age_secs}s{RESET}"
    )

    # ── ALERT ausgeben ──
    if alert:
        direction = "📈 RAUF" if lag_pct > 0 else "📉 RUNTER"
        print(f"\n{RED}{BOLD}{'═'*65}")
        print(f"  🚨  ALERT  —  LAG {direction}: {lag_pct:+.4f}%")
        print(f"  Schwelle: ±{ALERT_THRESHOLD}%  |  Spot: ${spot_price:,.2f}  |  Oracle: ${oracle_price:,.2f}")
        print(f"  → Oracle wird bald in Richtung {direction} aktualisieren")
        print(f"{'═'*65}{RESET}\n")


# ─── ORACLE POLLER (alle N Sekunden) ─────────────────────────────────────────
async def poll_oracle_loop():
    """Fragt Chainlink Oracle alle POLL_INTERVAL Sekunden ab."""
    print(f"{BLUE}[Oracle] Starte Polygon Verbindung...{RESET}")
    health_check_interval = 300  # 5 Minuten
    last_health_check = time.time()

    while True:
        round_id, oracle_price, updated_at = fetch_oracle_data()

        if oracle_price is not None:
            state["oracle_price"]   = oracle_price
            state["oracle_round"]   = round_id
            state["oracle_updated"] = updated_at

            # Nur loggen wenn wir auch einen Spot-Preis haben
            if state["spot_price"] is not None:
                lag_abs, lag_pct = calculate_lag(oracle_price, state["spot_price"])
                log_and_display(round_id, oracle_price, state["spot_price"], lag_abs, lag_pct)

        # Periodischer Health-Check alle 5 Minuten
        now = time.time()
        if now - last_health_check >= health_check_interval:
            uptime_secs = int(now - state["start_time"]) if state["start_time"] else 0
            uptime_min = uptime_secs // 60
            print(
                f"{CYAN}[Health] Uptime: {uptime_min}m  |  "
                f"Ticks geloggt: {state['total_ticks']}  |  "
                f"NTP-Offset: {ntp_offset:+.4f}s{RESET}"
            )
            last_health_check = now

        await asyncio.sleep(POLL_INTERVAL)


# ─── BINANCE WEBSOCKET (Echtzeit Spot) ───────────────────────────────────────
async def stream_binance_spot():
    """
    Binance WebSocket: BTC/USDT Ticker (24h rolling).
    'c' = aktueller Preis (letzter Trade).
    Reconnect automatisch bei Verbindungsproblemen.
    """
    ws_url = "wss://stream.binance.com:9443/ws/btcusdt@ticker"

    while True:
        try:
            print(f"{GREEN}[Binance] Verbinde WebSocket...{RESET}")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
                print(f"{GREEN}[Binance] ✓ Verbunden — Empfange BTC/USDT Preise{RESET}\n")
                async for raw_msg in ws:
                    data = json.loads(raw_msg)
                    state["spot_price"] = float(data["c"])  # "c" = letzter Preis

        except websockets.exceptions.ConnectionClosed:
            print(f"{YELLOW}[Binance] Verbindung getrennt — reconnecte in 3s...{RESET}")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"{RED}[Binance FEHLER] {e} — reconnecte in 5s...{RESET}")
            await asyncio.sleep(5)


# ─── HAUPTPROGRAMM ───────────────────────────────────────────────────────────
async def main():
    print(f"\n{BOLD}{BLUE}{'═'*65}")
    print(f"  🔍  ORACLE LAG MONITOR  —  PHASE 1")
    print(f"  Chainlink BTC/USD (Polygon) vs. Binance Spot")
    print(f"  Alert-Schwelle: ±{ALERT_THRESHOLD}%  |  Oracle-Poll: alle {POLL_INTERVAL}s")
    print(f"  Log-Datei: {LOG_FILE}")
    print(f"{'═'*65}{RESET}\n")

    # NTP Zeitsynchronisation messen
    measure_ntp_offset()
    state["start_time"] = time.time()

    # Web3 Verbindung testen
    if not w3.is_connected():
        print(f"{RED}[FEHLER] Polygon RPC nicht erreichbar!")
        print(f"  → config.json öffnen und polygon_rpc_url prüfen{RESET}")
        sys.exit(1)

    current_block = w3.eth.block_number
    print(f"{GREEN}[Web3] ✓ Polygon Mainnet verbunden  (Block #{current_block:,}){RESET}")

    # Einmalig Oracle testen
    round_id, price, updated = fetch_oracle_data()
    if price is None:
        print(f"{RED}[FEHLER] Chainlink Oracle nicht erreichbar. RPC URL prüfen!{RESET}")
        sys.exit(1)

    print(f"{GREEN}[Oracle] ✓ Chainlink BTC/USD erreichbar  (${price:,.2f}  Round #{round_id}){RESET}")
    print(f"{CYAN}[Info] Starte Monitoring... (CTRL+C zum Stoppen){RESET}\n")
    print(f"{'─'*65}")
    print(f"{'Timestamp':<22} {'Oracle':>12} {'Spot':>12} {'Lag':>11}  {'Round'}")
    print(f"{'─'*65}")

    # Beide Loops parallel starten
    await asyncio.gather(
        poll_oracle_loop(),
        stream_binance_spot()
    )


# ─── START ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[STOP] Monitor gestoppt.")
        print(f"  → Log gespeichert in: {LOG_FILE}{RESET}")
        csv_file.close()
        sys.exit(0)
