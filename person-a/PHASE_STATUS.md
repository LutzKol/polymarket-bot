# Phase Status Tracker

## Current Phase
- Active phase: **Phase 1 — Oracle Lag Monitor**
- Date: **2026-02-21**

## Phase 1 Checklist (Roadmap-Aligned)
- [ ] (A) Oracle lag monitor runs stably for 48h without crash
- [ ] (A) CSV log contains at least 48h of data (oracle + spot + lag)
- [ ] (A/B) At least 2 lag events > 0.3% are documented and understood
- [x] (B support completed) Polymarket API connection successfully tested
- [ ] (B) 30 days of historical Chainlink data downloaded and analyzed

## Implemented in Repo
- [x] Realtime oracle vs spot monitor (`/Users/s1/Desktop/Polymarketbot/oracle_monitor.py`)
- [x] CSV logging (`/Users/s1/Desktop/Polymarketbot/oracle_lag_log.csv`)
- [x] Console alerting threshold config (`/Users/s1/Desktop/Polymarketbot/config.json`)
- [x] Lag-event analysis utility (`/Users/s1/Desktop/Polymarketbot/analyze_lag_events.py`)
- [x] Polymarket connectivity test utility (`/Users/s1/Desktop/Polymarketbot/check_polymarket_connectivity.py`)
- [x] Run-control scripts (`/Users/s1/Desktop/Polymarketbot/start_phase1_monitor.sh`, `/Users/s1/Desktop/Polymarketbot/status_phase1_monitor.sh`, `/Users/s1/Desktop/Polymarketbot/stop_phase1_monitor.sh`)
- [x] Watchdog script (`/Users/s1/Desktop/Polymarketbot/phase1_watchdog.sh`)
- [x] Progress report utility (`/Users/s1/Desktop/Polymarketbot/phase1_progress_report.py`)
- [ ] Historical Chainlink 30d utility

## Phase 2 Preparation (Person A)
- [x] WebSocket manager skeleton (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/ws_manager.py`)
- [x] Unified state store (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/state_store.py`)
- [x] OBI + CVD feature helpers (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/features.py`)
- [x] Feature extractor for Phase-3 handoff (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/feature_extractor.py`)
- [x] Live feature CSV exporter (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/feature_exporter.py`)
- [x] Polymarket CLOB parser + poller (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/polymarket_client.py`)
- [x] Funding-rate poller (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/funding_client.py`)
- [x] 5m time feature helper (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/time_utils.py`)
- [x] Runner integration for Polymarket (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/live_runner.py`)
- [x] Runner integration for funding + seconds_remaining (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/live_runner.py`)
- [x] Exported Polymarket fields for handoff (`pm_best_bid`, `pm_best_ask`, `pm_mid_prob`, `pm_spread`, `pm_obi`)
- [x] Exported time/funding fields for handoff (`tau`, `tau_sq`, `funding_rate`)
- [x] Data quality report utility (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/data_quality_report.py`)
- [x] Unit tests for OBI/CVD/state (`/Users/s1/Desktop/Polymarketbot/tests/test_features.py`, `/Users/s1/Desktop/Polymarketbot/tests/test_state_store.py`)
- [x] Live pipeline runner (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/live_runner.py`)

## Phase Gate
- Rule: Do not move to Phase 2 until all Phase 1 checklist items are complete.

## Evidence (2026-02-21)
- `python3 check_polymarket_connectivity.py` => PASS (Gamma API 200, CLOB API 200)
- `python3 -u oracle_monitor.py` => live run verified (Web3 + Oracle + Binance connected; ticks logged)
- `python3 analyze_lag_events.py` => 4 ticks analyzed, 0 events > 0.3% so far
- `bash start_phase1_monitor.sh && bash status_phase1_monitor.sh && bash stop_phase1_monitor.sh` => run-control workflow verified
- `python3 phase1_progress_report.py` => Fortschrittsreport aus CSV verifiziert
- `bash phase1_watchdog.sh --once` => erkennt extern laufenden Monitor korrekt (`EXTERNAL_ACTIVE`)
- `python3 -m unittest discover -s tests -v` => 8/8 Tests OK
- `python3 phase1_progress_report.py` => 2628 Datenzeilen, 2.08h Fenster, Events >0.3%: 0
- `python3 phase2_pipeline/live_runner.py --duration-seconds 6 --heartbeat-seconds 1` => Oracle + Binance Ticker/AggTrade/Depth live, OBI/CVD/Lag Heartbeats ok
- `python3 -m unittest discover -s tests -v` => 10/10 Tests OK
- `python3 phase2_pipeline/feature_exporter.py --duration-seconds 8 --output-csv data/phase3_features_live.csv` => exportiert modellfähiges Feature-CSV
- `python3 -m unittest discover -s tests -v` => 13/13 Tests OK
- `python3 phase2_pipeline/live_runner.py --duration-seconds 8 --polymarket-token-id <valid_token_id>` => Polymarket pm_mid/pm_obi live verifiziert
- `python3 phase2_pipeline/feature_exporter.py --duration-seconds 6 --polymarket-token-id <valid_token_id> --output-csv data/phase3_features_with_pm.csv` => pm_* Spalten in CSV befüllt
- `python3 phase2_pipeline/data_quality_report.py --csv data/phase3_features_with_pm.csv` => Quality-Check erstellt (Rows/Intervalle/Missing/Gaps)
- `python3 -m unittest discover -s tests -v` => 17/17 Tests OK (inkl. Funding + Time Utils)
- `python3 phase2_pipeline/feature_exporter.py --duration-seconds 10 --funding-poll-seconds 2 --polymarket-token-id <valid_token_id> --output-csv data/phase3_features_full.csv` => funding_rate + tau/tau_sq + pm_* live befüllt
- `python3 -m unittest discover -s tests -v` => 68/68 Tests OK (inkl. Phase 5 paper trading + fill simulation)

## Phase 5 Preparation (Person A) - Implemented
- [x] Paper-Trading Engine (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/paper_trading.py`)
- [x] Fill-Simulation (Spread/Slippage/Latency assumptions in bps)
- [x] Binary event settlement resolution (YES/NO payout at resolution)
- [x] Realized PnL + return% + bankroll tracking
- [x] RiskManager outcome feedback integration (Brier + consecutive losses)
- [x] Trade summary metrics (win rate, PnL, drawdown)
- [x] Unit Tests (`/Users/s1/Desktop/Polymarketbot/tests/test_paper_trading.py`)
- [x] Replay-Runner (Signal CSV + Label CSV -> Paper Trades + Summary) (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/paper_trade_replay.py`)
- [x] Offline Signal-Exporter (Feature CSV -> `trade_signals.csv`) (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/signal_exporter.py`)
- [x] Dynamische Polymarket Token-Rotation (Gamma -> aktueller BTC 5m Token) (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/polymarket_client.py`)
- [x] Paper-Risk Limits (Daily Loss Stop / Cooldown / Max Trades pro Tag) (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/paper_trading.py`)
- [x] Variables Polymarket Fee-Modell im Fill/PnL-Replay (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/paper_trading.py`, `/Users/s1/Desktop/Polymarketbot/phase2_pipeline/paper_trade_replay.py`)
- [x] Discord-/Telegram-Alerts bei Trade-Vorschlägen (Dedupe + Throttle) (`/Users/s1/Desktop/Polymarketbot/phase2_pipeline/signal_alerts.py`, integriert in `/Users/s1/Desktop/Polymarketbot/phase2_pipeline/live_runner.py`)

## Phase 5 Still Needed For Official Validation
- [ ] Connect live model outputs (Person B model / calibrated thresholds)
- [ ] Wire event lifecycle source (open/close resolution timestamps per market)
- [ ] Run paper-trading campaign (target: 200 trades per roadmap)
- [ ] Evaluate Phase 5 acceptance metrics on paper results

## Latest Validation
- `python3 -m unittest discover -s tests -v` => 92/92 Tests OK (inkl. Signal Alerts)
- `python3 -u phase2_pipeline/feature_exporter.py --polymarket-auto-rotate true --duration-seconds 12 ...` => PM Auto-Rotation live verifiziert (`rotated token`, `pm_*` befüllt)
