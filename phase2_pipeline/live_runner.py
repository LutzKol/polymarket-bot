#!/usr/bin/env python3
"""Live Phase-2 pipeline runner (Person A).

Feeds:
- Chainlink BTC/USD (Polygon) via polling
- Binance ticker (spot)
- Binance aggTrade (CVD input)
- Binance depth5 (orderbook input for OBI)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.exceptions import Web3Exception

try:
    from phase2_pipeline.ev_engine import (
        EVCalculator,
        KellySizer,
        ModelLoader,
        RiskManager,
        evaluate_signal,
    )
    from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
    from phase2_pipeline.feature_normalizer import FeatureNormalizer
    from phase2_pipeline.features import calculate_obi
    from phase2_pipeline.funding_client import FundingRatePoller
    from phase2_pipeline.paper_trading import (
        FillConfig,
        FillSimulator,
        PaperRiskLimits,
        PaperTrade,
        PaperTradingEngine,
    )
    from phase2_pipeline.polymarket_client import PolymarketBookPoller, RotatingPolymarketBookPoller
    from phase2_pipeline.signal_alerts import (
        SignalAlertConfig,
        SignalAlertNotifier,
        format_daily_reset,
        format_kill_switch,
        format_paper_trade_opened,
        format_paper_trade_resolved,
    )
    from phase2_pipeline.state_store import UnifiedStateStore
    from phase2_pipeline.time_utils import seconds_remaining_in_5m_window
    from phase2_pipeline.trade_signal import TradeSignal
    from phase2_pipeline.ws_manager import FeedConfig, WebSocketManager
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from phase2_pipeline.ev_engine import (
        EVCalculator,
        KellySizer,
        ModelLoader,
        RiskManager,
        evaluate_signal,
    )
    from phase2_pipeline.feature_extractor import FEATURE_COLUMNS, FeatureExtractor
    from phase2_pipeline.feature_normalizer import FeatureNormalizer
    from phase2_pipeline.features import calculate_obi
    from phase2_pipeline.funding_client import FundingRatePoller
    from phase2_pipeline.paper_trading import (
        FillConfig,
        FillSimulator,
        PaperRiskLimits,
        PaperTrade,
        PaperTradingEngine,
    )
    from phase2_pipeline.polymarket_client import PolymarketBookPoller, RotatingPolymarketBookPoller
    from phase2_pipeline.signal_alerts import (
        SignalAlertConfig,
        SignalAlertNotifier,
        format_daily_reset,
        format_kill_switch,
        format_paper_trade_opened,
        format_paper_trade_resolved,
    )
    from phase2_pipeline.state_store import UnifiedStateStore
    from phase2_pipeline.time_utils import seconds_remaining_in_5m_window
    from phase2_pipeline.trade_signal import TradeSignal
    from phase2_pipeline.ws_manager import FeedConfig, WebSocketManager

CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Phase2LiveRunner:
    def __init__(
        self,
        *,
        rpc_url: str,
        chainlink_address: str,
        oracle_poll_seconds: float = 5.0,
        heartbeat_seconds: float = 1.0,
        history_size: int = 1800,
        polymarket_token_id: Optional[str] = None,
        polymarket_poll_seconds: float = 1.0,
        polymarket_base_url: str = "https://clob.polymarket.com",
        polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com",
        polymarket_auto_rotate: bool = False,
        polymarket_rotate_check_seconds: float = 15.0,
        funding_enabled: bool = True,
        funding_symbol: str = "BTCUSDT",
        funding_poll_seconds: float = 30.0,
        funding_base_url: str = "https://fapi.binance.com",
        max_oracle_age_seconds: float = 300.0,
        # Phase 4: EV-Engine params
        model_path: str = "",
        model_feature_columns: Optional[list[str]] = None,
        bankroll_usdc: float = 1000.0,
        max_fraction_per_trade: float = 0.02,
        ev_threshold: float = 0.02,
        brier_gate: float = 0.24,
        max_consecutive_losses: int = 3,
        signal_csv_path: str = "data/trade_signals.csv",
        trade_alerts_enabled: bool = False,
        trade_alert_provider: str = "",
        discord_webhook_url: str = "",
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        trade_alert_only_actionable: bool = True,
        trade_alert_min_interval_seconds: float = 30.0,
        trade_alert_dedupe_by_bucket: bool = True,
        # Phase 5: Paper Trading
        paper_trading_enabled: bool = False,
        paper_trades_csv_path: str = "data/paper_trades.csv",
        paper_fill_config: Optional[FillConfig] = None,
        paper_risk_limits: Optional[PaperRiskLimits] = None,
    ):
        self.oracle_poll_seconds = oracle_poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.max_oracle_age_seconds = max_oracle_age_seconds
        self.oracle_stale = False
        self.stop_event: Optional[asyncio.Event] = None
        self.state = UnifiedStateStore(history_size=history_size)
        self.ws_manager = WebSocketManager(logger=self._log)

        self.w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        self.chainlink_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(chainlink_address),
            abi=CHAINLINK_ABI,
        )
        self.chainlink_decimals = 8

        self.total_oracle_ticks = 0
        self.total_spot_ticks = 0
        self.total_trade_ticks = 0
        self.total_depth_ticks = 0
        self.total_pm_ticks = 0
        self.total_funding_ticks = 0

        self.polymarket_poller: Optional[PolymarketBookPoller] = None
        if polymarket_token_id:
            self.polymarket_poller = PolymarketBookPoller(
                token_id=polymarket_token_id,
                base_url=polymarket_base_url,
                poll_seconds=polymarket_poll_seconds,
                logger=self._log,
            )
        elif polymarket_auto_rotate:
            self.polymarket_poller = RotatingPolymarketBookPoller(
                base_url=polymarket_base_url,
                gamma_base_url=polymarket_gamma_base_url,
                poll_seconds=polymarket_poll_seconds,
                rotate_check_seconds=polymarket_rotate_check_seconds,
                logger=self._log,
            )

        self.funding_poller: Optional[FundingRatePoller] = None
        if funding_enabled:
            self.funding_poller = FundingRatePoller(
                symbol=funding_symbol,
                base_url=funding_base_url,
                poll_seconds=funding_poll_seconds,
                logger=self._log,
            )

        # Phase 4: EV-Engine initialization
        self.ev_enabled = False
        self.bankroll_usdc = bankroll_usdc
        self.signal_csv_path = signal_csv_path
        self.signal_alert_notifier: Optional[SignalAlertNotifier] = None
        alert_cfg = SignalAlertConfig(
            enabled=bool(trade_alerts_enabled),
            provider=str(trade_alert_provider or ""),
            discord_webhook_url=str(discord_webhook_url or ""),
            telegram_bot_token=str(telegram_bot_token or ""),
            telegram_chat_id=str(telegram_chat_id or ""),
            actionable_only=bool(trade_alert_only_actionable),
            min_interval_seconds=float(trade_alert_min_interval_seconds),
            dedupe_by_bucket=bool(trade_alert_dedupe_by_bucket),
        )
        _alert_notifier = SignalAlertNotifier(alert_cfg)
        if _alert_notifier.is_enabled():
            self.signal_alert_notifier = _alert_notifier

        if model_path:
            try:
                feature_cols = model_feature_columns or FEATURE_COLUMNS
                self.model_loader = ModelLoader(model_path, feature_cols)
                self.ev_calculator = EVCalculator(ev_threshold=ev_threshold)
                self.kelly_sizer = KellySizer(max_fraction=max_fraction_per_trade)
                self.risk_manager = RiskManager(
                    max_consecutive_losses=max_consecutive_losses,
                    brier_gate=brier_gate,
                    max_fraction=max_fraction_per_trade,
                )
                self.feature_extractor = FeatureExtractor()
                self.feature_normalizer = FeatureNormalizer()
                self.ev_enabled = True
            except FileNotFoundError as exc:
                self._log(f"[EV] Model file not found, EV disabled: {exc}")

        # Phase 5: Paper Trading initialization
        self.paper_trading_enabled = False
        self.paper_engine: Optional[PaperTradingEngine] = None
        self.paper_trades_csv_path = paper_trades_csv_path
        self._current_bucket_id: Optional[int] = None
        self._bucket_start_oracle_price: Optional[float] = None
        self._current_day_key: Optional[str] = None

        if paper_trading_enabled and self.ev_enabled:
            self.paper_engine = PaperTradingEngine(
                starting_bankroll_usdc=bankroll_usdc,
                fill_simulator=FillSimulator(paper_fill_config or FillConfig()),
                risk_manager=self.risk_manager if hasattr(self, "risk_manager") else None,
                risk_limits=paper_risk_limits or PaperRiskLimits(),
            )
            self.paper_trading_enabled = True

    def _log(self, message: str) -> None:
        print(f"[{_utc_iso()}] {message}")

    def _get_stop_event(self) -> asyncio.Event:
        if self.stop_event is None:
            self.stop_event = asyncio.Event()
        return self.stop_event

    def _init_signal_csv(self) -> None:
        """Write CSV header if the signal file does not exist yet."""
        path = Path(self.signal_csv_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(TradeSignal.csv_columns())

    def _log_signal(self, signal: TradeSignal) -> None:
        """Append a trade signal row to the CSV file."""
        path = Path(self.signal_csv_path)
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            row = signal.to_dict()
            writer.writerow([row[col] for col in TradeSignal.csv_columns()])
            f.flush()

    async def _maybe_alert_signal(self, signal: TradeSignal) -> None:
        if self.signal_alert_notifier is None:
            return
        try:
            sent, reason = await asyncio.to_thread(self.signal_alert_notifier.notify, signal)
            if sent:
                self._log(f"[ALERT] sent ({self.signal_alert_notifier.config.provider})")
            elif reason not in {"not_actionable", "duplicate_bucket", "throttled"}:
                self._log(f"[ALERT] skipped ({reason})")
        except Exception as exc:
            self._log(f"[ALERT] error: {exc}")

    def _init_paper_trades_csv(self) -> None:
        """Write CSV header if the paper trades file does not exist yet."""
        path = Path(self.paper_trades_csv_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(PaperTrade.csv_columns())

    def _log_paper_trade(self, trade: PaperTrade) -> None:
        """Append a resolved paper trade row to the CSV file."""
        path = Path(self.paper_trades_csv_path)
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            row = trade.to_dict()
            writer.writerow([row[col] for col in PaperTrade.csv_columns()])
            f.flush()

    def _has_open_paper_trade(self) -> bool:
        return self.paper_engine is not None and self.paper_engine.has_open_trades()

    def _has_open_paper_trade_in_bucket(self, bucket_id: int) -> bool:
        if self.paper_engine is None:
            return False
        return self.paper_engine.open_trade_for_bucket(str(bucket_id)) is not None

    async def _maybe_alert_paper_trade_opened(self, trade: PaperTrade) -> None:
        if self.signal_alert_notifier is None:
            return
        msg = format_paper_trade_opened(trade)
        try:
            provider = self.signal_alert_notifier.config.provider
            await asyncio.to_thread(
                self.signal_alert_notifier._send, provider, msg
            )
        except Exception:
            pass

    async def _maybe_alert_paper_trade(self, trade: PaperTrade) -> None:
        if self.signal_alert_notifier is None or self.paper_engine is None:
            return
        summary = self.paper_engine.summary()
        msg = format_paper_trade_resolved(trade, summary)
        try:
            provider = self.signal_alert_notifier.config.provider
            await asyncio.to_thread(
                self.signal_alert_notifier._send, provider, msg
            )
        except Exception:
            pass

    async def _maybe_alert_kill_switch(self, reason: str) -> None:
        if self.paper_engine is None:
            return
        summary = self.paper_engine.summary()
        self._log(f"[KILL-SWITCH] ACTIVATED: {reason}")
        if self.signal_alert_notifier is None:
            return
        msg = format_kill_switch(reason, summary)
        try:
            provider = self.signal_alert_notifier.config.provider
            await asyncio.to_thread(
                self.signal_alert_notifier._send, provider, msg
            )
        except Exception:
            pass

    async def _maybe_alert_daily_reset(self, prev_day_key: str) -> None:
        if self.paper_engine is None:
            return
        day_summary = self.paper_engine.daily_summary(prev_day_key)
        overall_summary = self.paper_engine.summary()
        self.paper_engine.reset_cooldown()
        self._log(
            f"[PAPER] daily reset: {day_summary['wins']}W/{day_summary['losses']}L "
            f"pnl=${day_summary['pnl_usdc']:+.2f} bankroll=${overall_summary['ending_bankroll_usdc']:,.2f}"
        )
        if self.signal_alert_notifier is None:
            return
        msg = format_daily_reset(day_summary, overall_summary)
        try:
            provider = self.signal_alert_notifier.config.provider
            await asyncio.to_thread(
                self.signal_alert_notifier._send, provider, msg
            )
        except Exception:
            pass

    def _fetch_oracle_blocking(self) -> tuple[int, float, int]:
        raw = self.chainlink_contract.functions.latestRoundData().call()
        round_id = int(raw[0])
        price = float(raw[1]) / (10 ** self.chainlink_decimals)
        updated_at = int(raw[3])
        return round_id, price, updated_at

    async def poll_oracle_loop(self) -> None:
        stop_event = self._get_stop_event()
        while not stop_event.is_set():
            try:
                round_id, price, updated_at = await asyncio.wait_for(
                    asyncio.to_thread(self._fetch_oracle_blocking),
                    timeout=8.0,
                )
                self.state.update_oracle(price=price, round_id=round_id, updated_at=updated_at)
                self.total_oracle_ticks += 1
            except asyncio.TimeoutError:
                self._log("[ORACLE] timeout while fetching latestRoundData")
            except (Web3Exception, OSError, ConnectionError) as exc:
                self._log(f"[ORACLE] web3/network error: {exc}")
            except Exception as exc:
                self._log(f"[ORACLE] unexpected error: {exc}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.oracle_poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def heartbeat_loop(self) -> None:
        stop_event = self._get_stop_event()
        while not stop_event.is_set():
            self.state.update_seconds_remaining(seconds_remaining_in_5m_window())
            oracle = self.state.oracle_prices[-1] if self.state.oracle_prices else None
            spot = self.state.spot_prices[-1] if self.state.spot_prices else None
            lag_pct: Optional[float] = None
            if oracle and spot:
                lag_pct = ((spot - oracle) / oracle) * 100.0

            obi = calculate_obi(self.state.orderbook)
            pm_obi = calculate_obi(self.state.polymarket_orderbook)
            cvd_60s = self.state.cvd_window(60)

            oracle_age = "n/a"
            oracle_stale = False
            if self.state.oracle_updated_at:
                age_seconds = int(datetime.now(timezone.utc).timestamp()) - int(self.state.oracle_updated_at)
                oracle_age = str(age_seconds)
                if age_seconds > self.max_oracle_age_seconds:
                    oracle_stale = True
                    self._log(
                        f"[ORACLE] WARNING: oracle stale (age={age_seconds}s > "
                        f"max={self.max_oracle_age_seconds}s) — skipping feature export"
                    )
            self.oracle_stale = oracle_stale

            oracle_str = f"{oracle:,.2f}" if oracle is not None else "n/a"
            spot_str = f"{spot:,.2f}" if spot is not None else "n/a"
            lag_str = f"{lag_pct:+.4f}%" if lag_pct is not None else "n/a"
            obi_str = f"{obi:+.4f}" if obi is not None else "n/a"
            pm_obi_str = f"{pm_obi:+.4f}" if pm_obi is not None else "n/a"
            pm_mid_str = (
                f"{self.state.pm_mid_prob:.4f}" if self.state.pm_mid_prob is not None else "n/a"
            )
            pm_spread_str = (
                f"{self.state.pm_spread:.4f}" if self.state.pm_spread is not None else "n/a"
            )
            funding_str = (
                f"{self.state.funding_rate:+.6f}" if self.state.funding_rate is not None else "n/a"
            )
            secs_remaining_str = (
                f"{self.state.seconds_remaining:.1f}"
                if self.state.seconds_remaining is not None
                else "n/a"
            )

            self._log(
                "[HEARTBEAT] "
                f"oracle={oracle_str} spot={spot_str} lag={lag_str} "
                f"obi={obi_str} pm_obi={pm_obi_str} pm_mid={pm_mid_str} pm_spread={pm_spread_str} "
                f"cvd_60s={cvd_60s:+.4f} funding={funding_str} secs_remaining={secs_remaining_str} "
                f"oracle_age_s={oracle_age} "
                f"ticks(o/s/t/d/pm/f)={self.total_oracle_ticks}/{self.total_spot_ticks}/{self.total_trade_ticks}/{self.total_depth_ticks}/{self.total_pm_ticks}/{self.total_funding_ticks}"
            )

            # Phase 4: EV-Engine evaluation
            signal: Optional[TradeSignal] = None
            if self.ev_enabled and not oracle_stale:
                try:
                    snapshot = self.state.snapshot()
                    snapshot["cvd_60s"] = cvd_60s
                    features = self.feature_extractor.extract(snapshot)
                    self.feature_normalizer.update(features)
                    normalized = self.feature_normalizer.normalize(features)

                    market_prob = self.state.pm_mid_prob if self.state.pm_mid_prob is not None else 0.5

                    signal = evaluate_signal(
                        features=normalized,
                        model=self.model_loader,
                        market_prob=market_prob,
                        bankroll=self.bankroll_usdc,
                        risk_manager=self.risk_manager,
                        ev_calculator=self.ev_calculator,
                        kelly_sizer=self.kelly_sizer,
                        oracle_stale=oracle_stale,
                    )
                    self._log_signal(signal)
                    await self._maybe_alert_signal(signal)
                    self._log(
                        f"[EV] dir={signal.direction} p_model={signal.model_probability:.4f} "
                        f"p_mkt={signal.market_probability:.4f} ev={signal.ev:.4f} "
                        f"kelly={signal.kelly_fraction:.4f} size=${signal.suggested_size_usdc:.2f} "
                        f"risk_ok={signal.risk_checks_passed}"
                    )
                except Exception as exc:
                    self._log(f"[EV] error during evaluation: {exc}")
            elif self.ev_enabled:
                self._log("[EV] skipped — oracle stale")

            # Phase 5: Paper Trading — bucket tracking and trade lifecycle
            if self.paper_trading_enabled and self.paper_engine is not None and oracle is not None:
                now_ts = int(datetime.now(timezone.utc).timestamp())
                bucket_id = now_ts // 300

                # Daily reset at 00:00 UTC
                day_key = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                if self._current_day_key is not None and day_key != self._current_day_key:
                    await self._maybe_alert_daily_reset(self._current_day_key)
                self._current_day_key = day_key

                # Bucket changed? Resolve open trade from previous bucket
                if self._current_bucket_id is not None and bucket_id != self._current_bucket_id:
                    if self._has_open_paper_trade() and self._bucket_start_oracle_price is not None:
                        end_price = oracle
                        outcome_up = end_price > self._bucket_start_oracle_price
                        try:
                            trade = self.paper_engine.resolve_open_trade(outcome_up)
                            self._log_paper_trade(trade)
                            outcome_str = "WON" if trade.won else "LOST"
                            self._log(
                                f"[PAPER] resolved trade #{trade.trade_id}: {outcome_str} "
                                f"pnl=${trade.pnl_usdc:+.2f} dir={trade.direction}"
                            )
                            await self._maybe_alert_paper_trade(trade)
                            # Check kill-switch after resolution
                            if not self.paper_engine.kill_switch_triggered:
                                triggered, ks_reason = self.paper_engine.check_kill_switch()
                                if not triggered and hasattr(self, "risk_manager"):
                                    rb = self.risk_manager.rolling_brier
                                    if rb is not None and rb > self.risk_manager.brier_gate:
                                        ks_reason = (
                                            f"Brier score exceeded threshold "
                                            f"({rb:.3f} > {self.risk_manager.brier_gate})"
                                        )
                                        self.paper_engine.kill_switch_triggered = True
                                        self.paper_engine.kill_switch_reason = ks_reason
                                        triggered = True
                                if triggered:
                                    await self._maybe_alert_kill_switch(ks_reason)
                        except Exception as exc:
                            self._log(f"[PAPER] error resolving trade: {exc}")

                # Update bucket tracking
                if self._current_bucket_id is None or bucket_id != self._current_bucket_id:
                    self._current_bucket_id = bucket_id
                    self._bucket_start_oracle_price = oracle

                # Open new trade?
                if signal is not None and signal.direction in ("UP", "DOWN") and signal.risk_checks_passed:
                    if not self._has_open_paper_trade_in_bucket(bucket_id):
                        paper_trade = self.paper_engine.open_trade(
                            signal=signal,
                            event_id=str(bucket_id),
                            pm_best_bid=self.state.pm_best_bid,
                            pm_best_ask=self.state.pm_best_ask,
                        )
                        if paper_trade is not None:
                            self._log(
                                f"[PAPER] opened trade #{paper_trade.trade_id}: "
                                f"dir={paper_trade.direction} entry={paper_trade.entry_price:.4f} "
                                f"size=${paper_trade.size_usdc:.2f} bucket={bucket_id}"
                            )
                            await self._maybe_alert_paper_trade_opened(paper_trade)
                        elif self.paper_engine.last_reject_reason:
                            self._log(
                                f"[PAPER] trade rejected: {self.paper_engine.last_reject_reason}"
                            )

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.heartbeat_seconds)
            except asyncio.TimeoutError:
                pass

    async def on_ticker(self, payload: dict) -> None:
        price = float(payload["c"])
        self.state.update_spot(price)
        self.total_spot_ticks += 1

    async def on_agg_trade(self, payload: dict) -> None:
        # Binance aggTrade "m" == True means buyer is maker -> aggressor is sell.
        qty = float(payload["q"])
        side = "sell" if payload.get("m") else "buy"
        self.state.add_trade(side=side, qty=qty)
        self.total_trade_ticks += 1

    async def on_depth(self, payload: dict) -> None:
        bids = payload.get("bids", payload.get("b", []))
        asks = payload.get("asks", payload.get("a", []))
        self.state.update_orderbook(bids=bids, asks=asks)
        self.total_depth_ticks += 1

    def on_polymarket_book(self, book: dict) -> None:
        self.state.update_polymarket_orderbook(
            bids=book.get("bids", []),
            asks=book.get("asks", []),
            best_bid=book.get("best_bid"),
            best_ask=book.get("best_ask"),
            mid_prob=book.get("implied_mid_prob"),
            spread=book.get("spread"),
        )
        self.total_pm_ticks += 1

    def on_funding_rate(self, rate: float) -> None:
        self.state.update_funding_rate(rate)
        self.total_funding_ticks += 1

    async def run(self) -> None:
        self._log("[BOOT] Phase-2 live runner starting")
        if not self.w3.is_connected():
            raise RuntimeError("Polygon RPC not reachable (w3.is_connected() is False)")

        block_no = self.w3.eth.block_number
        self._log(f"[BOOT] Polygon connected (block={block_no})")

        if self.ev_enabled:
            self._init_signal_csv()
            self._log(f"[EV] EV Engine enabled (model loaded, signals → {self.signal_csv_path})")
        else:
            self._log("[EV] EV Engine disabled (no model_path)")

        if self.paper_trading_enabled and self.paper_engine is not None:
            self._init_paper_trades_csv()
            self._log(
                f"[PAPER] Paper trading enabled "
                f"(bankroll=${self.paper_engine.starting_bankroll_usdc:.0f}, "
                f"trades -> {self.paper_trades_csv_path})"
            )
        else:
            self._log("[PAPER] Paper trading disabled")

        if self.signal_alert_notifier is not None:
            cfg = self.signal_alert_notifier.config
            self._log(
                "[ALERT] enabled "
                f"(provider={cfg.provider}, actionable_only={cfg.actionable_only}, "
                f"min_interval={cfg.min_interval_seconds}s, dedupe_by_bucket={cfg.dedupe_by_bucket})"
            )
        else:
            self._log("[ALERT] disabled")

        feeds = [
            FeedConfig(
                name="binance_ticker",
                url="wss://stream.binance.com:9443/ws/btcusdt@ticker",
                on_message=self.on_ticker,
            ),
            FeedConfig(
                name="binance_aggTrade",
                url="wss://stream.binance.com:9443/ws/btcusdt@aggTrade",
                on_message=self.on_agg_trade,
            ),
            FeedConfig(
                name="binance_depth5",
                url="wss://stream.binance.com:9443/ws/btcusdt@depth5@100ms",
                on_message=self.on_depth,
            ),
        ]

        tasks = [
            self.poll_oracle_loop(),
            self.heartbeat_loop(),
            self.ws_manager.run_all(feeds),
        ]
        if self.polymarket_poller is not None:
            tasks.append(self.polymarket_poller.run(self._get_stop_event(), self.on_polymarket_book))
            if isinstance(self.polymarket_poller, RotatingPolymarketBookPoller):
                self._log("[PM] enabled (REST poller, dynamic token rotation)")
            else:
                self._log("[PM] enabled (REST poller)")
        else:
            self._log("[PM] disabled (set polymarket_token_id in config to enable)")

        if self.funding_poller is not None:
            tasks.append(self.funding_poller.run(self._get_stop_event(), self.on_funding_rate))
            self._log("[FUNDING] enabled (Binance premiumIndex poller)")
        else:
            self._log("[FUNDING] disabled")

        await asyncio.gather(*tasks)

    async def shutdown(self) -> None:
        self._get_stop_event().set()
        self.ws_manager.stop()


def load_config(path: Path) -> dict:
    from phase2_pipeline.config_validator import validate_config

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return validate_config(raw)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-2 live data pipeline")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--oracle-poll-seconds", type=float, default=None, help="Oracle poll interval")
    parser.add_argument("--heartbeat-seconds", type=float, default=1.0, help="Console heartbeat interval")
    parser.add_argument("--history-size", type=int, default=1800, help="State history size")
    parser.add_argument("--polymarket-token-id", default=None, help="Polymarket token id for /book polling")
    parser.add_argument(
        "--polymarket-auto-rotate",
        type=str,
        default=None,
        help="Auto-discover/rotate BTC 5m Polymarket token via Gamma API (true/false)",
    )
    parser.add_argument("--polymarket-poll-seconds", type=float, default=None, help="Polymarket poll interval")
    parser.add_argument("--polymarket-base-url", default=None, help="Polymarket CLOB base URL")
    parser.add_argument("--polymarket-gamma-base-url", default=None, help="Polymarket Gamma API base URL")
    parser.add_argument(
        "--polymarket-rotate-check-seconds",
        type=float,
        default=None,
        help="How often to re-resolve dynamic BTC 5m token",
    )
    parser.add_argument("--funding-enabled", type=str, default=None, help="Enable funding poller: true/false")
    parser.add_argument("--funding-symbol", default=None, help="Funding symbol, e.g. BTCUSDT")
    parser.add_argument("--funding-poll-seconds", type=float, default=None, help="Funding poll interval")
    parser.add_argument("--funding-base-url", default=None, help="Funding API base URL")
    parser.add_argument("--trade-alerts-enabled", type=str, default=None, help="Enable trade alerts: true/false")
    parser.add_argument("--trade-alert-provider", default=None, help="discord or telegram")
    parser.add_argument("--discord-webhook-url", default=None, help="Discord webhook URL")
    parser.add_argument("--telegram-bot-token", default=None, help="Telegram bot token")
    parser.add_argument("--telegram-chat-id", default=None, help="Telegram chat ID")
    parser.add_argument(
        "--trade-alert-only-actionable",
        type=str,
        default=None,
        help="Send only actionable trade suggestions: true/false",
    )
    parser.add_argument(
        "--trade-alert-min-interval-seconds",
        type=float,
        default=None,
        help="Minimum seconds between alerts",
    )
    parser.add_argument(
        "--trade-alert-dedupe-by-bucket",
        type=str,
        default=None,
        help="Dedupe alerts per 5m bucket+direction: true/false",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Optional runtime cap for smoke tests",
    )
    return parser.parse_args()


async def _run_with_optional_timeout(runner: Phase2LiveRunner, duration_seconds: Optional[float]) -> None:
    if duration_seconds is None:
        await runner.run()
        return

    task = asyncio.create_task(runner.run())
    try:
        await asyncio.sleep(duration_seconds)
        print(f"[{_utc_iso()}] [BOOT] duration reached -> stopping runner")
    finally:
        await runner.shutdown()
        await task


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))

    poll_seconds = (
        args.oracle_poll_seconds
        if args.oracle_poll_seconds is not None
        else float(config.get("oracle_poll_seconds", 5))
    )

    polymarket_token_id = args.polymarket_token_id or config.get("polymarket_token_id")
    polymarket_poll_seconds = (
        args.polymarket_poll_seconds
        if args.polymarket_poll_seconds is not None
        else float(config.get("polymarket_poll_seconds", 1.0))
    )
    polymarket_base_url = (
        args.polymarket_base_url
        if args.polymarket_base_url is not None
        else str(config.get("polymarket_base_url", "https://clob.polymarket.com"))
    )
    polymarket_gamma_base_url = (
        args.polymarket_gamma_base_url
        if args.polymarket_gamma_base_url is not None
        else str(config.get("polymarket_gamma_base_url", "https://gamma-api.polymarket.com"))
    )
    polymarket_auto_rotate = bool(config.get("polymarket_auto_rotate", False))
    if args.polymarket_auto_rotate is not None:
        polymarket_auto_rotate = str(args.polymarket_auto_rotate).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    polymarket_rotate_check_seconds = (
        args.polymarket_rotate_check_seconds
        if args.polymarket_rotate_check_seconds is not None
        else float(config.get("polymarket_rotate_check_seconds", 15.0))
    )

    funding_enabled = config.get("funding_enabled", True)
    if args.funding_enabled is not None:
        funding_enabled = str(args.funding_enabled).strip().lower() in {"1", "true", "yes", "on"}
    funding_symbol = args.funding_symbol or str(config.get("funding_symbol", "BTCUSDT"))
    funding_poll_seconds = (
        args.funding_poll_seconds
        if args.funding_poll_seconds is not None
        else float(config.get("funding_poll_seconds", 30.0))
    )
    funding_base_url = (
        args.funding_base_url
        if args.funding_base_url is not None
        else str(config.get("funding_base_url", "https://fapi.binance.com"))
    )
    trade_alerts_enabled = bool(config.get("trade_alerts_enabled", False))
    if args.trade_alerts_enabled is not None:
        trade_alerts_enabled = str(args.trade_alerts_enabled).strip().lower() in {"1", "true", "yes", "on"}
    trade_alert_provider = (
        args.trade_alert_provider
        if args.trade_alert_provider is not None
        else str(config.get("trade_alert_provider", ""))
    )
    discord_webhook_url = (
        args.discord_webhook_url
        if args.discord_webhook_url is not None
        else str(config.get("discord_webhook_url", ""))
    )
    telegram_bot_token = (
        args.telegram_bot_token
        if args.telegram_bot_token is not None
        else str(config.get("telegram_bot_token", ""))
    )
    telegram_chat_id = (
        args.telegram_chat_id
        if args.telegram_chat_id is not None
        else str(config.get("telegram_chat_id", ""))
    )
    trade_alert_only_actionable = bool(config.get("trade_alert_only_actionable", True))
    if args.trade_alert_only_actionable is not None:
        trade_alert_only_actionable = str(args.trade_alert_only_actionable).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    trade_alert_min_interval_seconds = (
        args.trade_alert_min_interval_seconds
        if args.trade_alert_min_interval_seconds is not None
        else float(config.get("trade_alert_min_interval_seconds", 30.0))
    )
    trade_alert_dedupe_by_bucket = bool(config.get("trade_alert_dedupe_by_bucket", True))
    if args.trade_alert_dedupe_by_bucket is not None:
        trade_alert_dedupe_by_bucket = str(args.trade_alert_dedupe_by_bucket).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # Phase 4: EV-Engine config
    model_path = str(config.get("model_path", ""))
    model_feature_columns = config.get("model_feature_columns")
    if isinstance(model_feature_columns, list):
        model_feature_columns = [str(c) for c in model_feature_columns]

    # Phase 5: Paper Trading config
    paper_trading_enabled = bool(config.get("paper_trading_enabled", False))
    paper_trades_csv_path = str(config.get("paper_trades_csv_path", "data/paper_trades.csv"))
    paper_fill_config = FillConfig(
        half_spread_bps=float(config.get("paper_fill_half_spread_bps", 5)),
        slippage_bps=float(config.get("paper_fill_slippage_bps", 10)),
        latency_bps=float(config.get("paper_fill_latency_bps", 5)),
        use_variable_fees=bool(config.get("paper_fill_use_variable_fees", True)),
    )
    paper_risk_limits = PaperRiskLimits(
        max_daily_loss_fraction=float(config.get("paper_max_daily_loss_fraction", 0.08)),
        max_trades_per_day=int(config.get("paper_max_trades_per_day", 20)),
        cooldown_after_consecutive_losses=int(config.get("paper_cooldown_after_consecutive_losses", 3)),
        cooldown_minutes=float(config.get("paper_cooldown_minutes", 30.0)),
    )

    runner = Phase2LiveRunner(
        rpc_url=config["polygon_rpc_url"],
        chainlink_address=config.get("chainlink_address", "0xc907E116054Ad103354f2D350FD2514433D57F6f"),
        oracle_poll_seconds=poll_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
        history_size=args.history_size,
        polymarket_token_id=polymarket_token_id,
        polymarket_poll_seconds=polymarket_poll_seconds,
        polymarket_base_url=polymarket_base_url,
        polymarket_gamma_base_url=polymarket_gamma_base_url,
        polymarket_auto_rotate=polymarket_auto_rotate,
        polymarket_rotate_check_seconds=polymarket_rotate_check_seconds,
        funding_enabled=bool(funding_enabled),
        funding_symbol=funding_symbol,
        funding_poll_seconds=funding_poll_seconds,
        funding_base_url=funding_base_url,
        max_oracle_age_seconds=float(config.get("max_oracle_age_seconds", 300)),
        # Phase 4
        model_path=model_path,
        model_feature_columns=model_feature_columns,
        bankroll_usdc=float(config.get("bankroll_usdc", 1000.0)),
        max_fraction_per_trade=float(config.get("max_fraction_per_trade", 0.02)),
        ev_threshold=float(config.get("ev_threshold", 0.02)),
        brier_gate=float(config.get("brier_gate", 0.24)),
        max_consecutive_losses=int(config.get("max_consecutive_losses", 3)),
        signal_csv_path=str(config.get("signal_csv_path", "data/trade_signals.csv")),
        trade_alerts_enabled=trade_alerts_enabled,
        trade_alert_provider=trade_alert_provider,
        discord_webhook_url=discord_webhook_url,
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        trade_alert_only_actionable=trade_alert_only_actionable,
        trade_alert_min_interval_seconds=trade_alert_min_interval_seconds,
        trade_alert_dedupe_by_bucket=trade_alert_dedupe_by_bucket,
        # Phase 5
        paper_trading_enabled=paper_trading_enabled,
        paper_trades_csv_path=paper_trades_csv_path,
        paper_fill_config=paper_fill_config,
        paper_risk_limits=paper_risk_limits,
    )

    try:
        asyncio.run(_run_with_optional_timeout(runner, args.duration_seconds))
    except KeyboardInterrupt:
        print(f"\n[{_utc_iso()}] [BOOT] interrupted by user")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
