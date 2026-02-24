# Phase Status Tracker

## Current Phase
- Active phase: **Phase 5 — Paper Trading Validation**
- Date: **2026-02-24**

## Phase 1 — Oracle Lag Monitor (Complete)
- [x] (A) Oracle lag monitor runs stably for 48h without crash
- [x] (A) CSV log contains at least 48h of data (oracle + spot + lag)
- [x] (A/B) At least 2 lag events > 0.3% are documented and understood
- [x] (B support completed) Polymarket API connection successfully tested
- [ ] (B) 30 days of historical Chainlink data downloaded and analyzed

### Implemented
- [x] Realtime oracle vs spot monitor (`oracle_monitor.py`)
- [x] CSV logging (`oracle_lag_log.csv`)
- [x] Console alerting threshold config (`config.json`)
- [x] Lag-event analysis utility (`analyze_lag_events.py`)
- [x] Polymarket connectivity test utility (`check_polymarket_connectivity.py`)
- [x] Run-control scripts (`start_phase1_monitor.sh`, `status_phase1_monitor.sh`, `stop_phase1_monitor.sh`)
- [x] Watchdog script (`phase1_watchdog.sh`)
- [x] Progress report utility (`phase1_progress_report.py`)

## Phase 2 — Live Data Pipeline (Complete)
- [x] WebSocket manager (`phase2_pipeline/ws_manager.py`)
- [x] Unified state store (`phase2_pipeline/state_store.py`)
- [x] OBI + CVD feature helpers (`phase2_pipeline/features.py`)
- [x] Feature extractor for Phase-3 handoff (`phase2_pipeline/feature_extractor.py`)
- [x] Feature normalizer (`phase2_pipeline/feature_normalizer.py`)
- [x] Live feature CSV exporter (`phase2_pipeline/feature_exporter.py`)
- [x] Polymarket CLOB parser + poller with dynamic token rotation (`phase2_pipeline/polymarket_client.py`)
- [x] Funding-rate poller (`phase2_pipeline/funding_client.py`)
- [x] 5m time feature helper (`phase2_pipeline/time_utils.py`)
- [x] Data quality report utility (`phase2_pipeline/data_quality_report.py`)
- [x] Live pipeline runner (`phase2_pipeline/live_runner.py`)

## Phase 3 — Feature Engineering (Complete)
- [x] Feature columns defined (`phase2_pipeline/feature_extractor.py`)
- [x] Exported fields: `pm_best_bid`, `pm_best_ask`, `pm_mid_prob`, `pm_spread`, `pm_obi`
- [x] Exported fields: `tau`, `tau_sq`, `funding_rate`
- [x] Training data collected: 487 buckets (119k rows)
- [x] Labeling utility (`label_features.py`, `label_buckets.py`)

## Phase 4 — EV Engine + Signal Generation (Complete)
- [x] EV Calculator with configurable threshold (`phase2_pipeline/ev_engine.py`)
- [x] Kelly Criterion position sizer (`phase2_pipeline/ev_engine.py`)
- [x] Risk Manager with Brier gate + consecutive loss tracking (`phase2_pipeline/ev_engine.py`)
- [x] Model loader (`phase2_pipeline/ev_engine.py`)
- [x] Signal generation pipeline (`phase2_pipeline/ev_engine.py`)
- [x] Trade signal dataclass + CSV logging (`phase2_pipeline/trade_signal.py`)
- [x] Config validator (`phase2_pipeline/config_validator.py`)
- [x] Discord/Telegram alerts with dedupe + throttle (`phase2_pipeline/signal_alerts.py`)
- [x] Offline signal exporter (`phase2_pipeline/signal_exporter.py`)

## Phase 5 — Paper Trading (In Progress)
### Implemented
- [x] Paper-Trading Engine with fill simulation (`phase2_pipeline/paper_trading.py`)
- [x] Fill-Simulation (spread/slippage/latency in bps)
- [x] Binary event settlement resolution (YES/NO payout)
- [x] Realized PnL + return% + bankroll tracking
- [x] RiskManager outcome feedback (Brier + consecutive losses)
- [x] Trade summary metrics (win rate, PnL, max drawdown)
- [x] Paper-Risk Limits (daily loss stop, cooldown, max trades/day)
- [x] Variable Polymarket fee model in fill/PnL
- [x] Replay runner (`phase2_pipeline/paper_trade_replay.py`)
- [x] Paper trade opened/resolved/daily reset Telegram alerts
- [x] Live heartbeat integration (bucket tracking, trade lifecycle)
- [x] Paper dashboard (`paper_dashboard.py`)
- [x] Kill-switch with 4 trigger conditions (`phase2_pipeline/paper_trading.py`, `phase2_pipeline/live_runner.py`)
  - Win rate < 54% after 50+ trades
  - Max drawdown > 15%
  - Bankroll < 50% of starting
  - Brier score > 0.24 (rolling 100 trades)
- [x] Kill-switch Telegram/Discord alerts (`phase2_pipeline/signal_alerts.py`)
- [x] Kill-switch blocks new trades via policy rejection

### Still Needed For Validation
- [ ] Connect live model outputs (Person B model / calibrated thresholds)
- [ ] Wire event lifecycle source (open/close resolution timestamps per market)
- [ ] Run paper-trading campaign (target: 200 trades per roadmap)
- [ ] Evaluate Phase 5 acceptance metrics on paper results

### Acceptance Criteria (from Roadmap)
- Win rate > 54% on 200+ trades
- Brier score < 0.24
- Kill-switch never triggered during campaign
- If pass -> cleared for Phase 6 (go-live)

## Test Suite
- **118/118 tests passing** (2026-02-24)
- Test files:
  - `tests/test_features.py` — OBI, CVD
  - `tests/test_state_store.py` — Unified state store
  - `tests/test_time_utils.py` — 5m time features
  - `tests/test_funding_client.py` — Funding rate poller
  - `tests/test_ev_engine.py` — EV calculator, Kelly, risk manager
  - `tests/test_feature_extractor.py` — Feature extraction
  - `tests/test_polymarket_client.py` — Polymarket parser
  - `tests/test_signal_alerts.py` — Alert formatting + notifier
  - `tests/test_signal_exporter.py` — Offline signal export
  - `tests/test_paper_trading.py` — Paper engine + fill sim
  - `tests/test_live_paper_trading.py` — Live integration + kill-switch (26 tests)
  - `tests/test_paper_trade_replay.py` — Replay runner
  - `tests/test_label_features.py` — Labeling
  - `tests/test_integration.py` — Integration tests

## Model Training
- [x] Training script (`train_model.py`)
- [x] Baseline model (`models/model.json`)
- Training data: 487 labeled buckets, 119k feature rows
