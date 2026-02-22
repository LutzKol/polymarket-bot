"""Phase 5 paper-trading engine and fill simulation for binary markets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from phase2_pipeline.ev_engine import RiskManager
from phase2_pipeline.trade_signal import TradeSignal


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_to_epoch(ts: str) -> float:
    value = (ts or "").strip()
    if value.endswith("Z"):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _utc_day_key_from_epoch(ts_epoch: float) -> str:
    return datetime.fromtimestamp(ts_epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def polymarket_variable_fee_rate(price: float) -> float:
    """Approximate effective taker fee rate as function of probability price.

    Matches the person-b research table (~1.56% max at p=0.50).
    """
    p = max(0.0, min(1.0, float(price)))
    return 0.25 * (p * (1.0 - p)) ** 2


@dataclass
class FillConfig:
    """Execution assumptions used for paper fills."""

    half_spread_bps: float = 0.0
    slippage_bps: float = 0.0
    latency_bps: float = 0.0
    entry_fee_rate: float = 0.0
    exit_fee_rate: float = 0.0
    use_variable_fees: bool = False
    min_price: float = 0.001
    max_price: float = 0.999


@dataclass
class PaperRiskLimits:
    """Operational risk limits for paper trading (Person A implementation)."""

    max_daily_loss_fraction: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    cooldown_after_consecutive_losses: Optional[int] = None
    cooldown_minutes: float = 30.0


@dataclass
class PaperTrade:
    """One paper trade from signal to event resolution."""

    trade_id: int
    event_id: str
    opened_at: str
    closed_at: Optional[str]
    status: str  # "OPEN" / "CLOSED"
    direction: str  # "UP" / "DOWN"
    contract_side: str  # "YES" / "NO"
    entry_price: float  # probability price paid per share
    exit_price: Optional[float]  # 1.0/0.0 at resolution
    size_usdc: float  # premium spent (before fees)
    shares: float
    entry_fee_usdc: float
    exit_fee_usdc: float
    payout_usdc: float
    pnl_usdc: Optional[float]
    return_pct: Optional[float]
    won: Optional[bool]
    resolution_outcome_up: Optional[bool]
    model_probability: float
    market_probability_entry: float
    ev_entry: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def csv_columns() -> list[str]:
        return [
            "trade_id",
            "event_id",
            "opened_at",
            "closed_at",
            "status",
            "direction",
            "contract_side",
            "entry_price",
            "exit_price",
            "size_usdc",
            "shares",
            "entry_fee_usdc",
            "exit_fee_usdc",
            "payout_usdc",
            "pnl_usdc",
            "return_pct",
            "won",
            "resolution_outcome_up",
            "model_probability",
            "market_probability_entry",
            "ev_entry",
            "reason",
        ]


class FillSimulator:
    """Simple deterministic fill model using spread/slippage/latency bps."""

    def __init__(self, config: Optional[FillConfig] = None):
        self.config = config or FillConfig()

    def _clamp_price(self, price: float) -> float:
        return max(self.config.min_price, min(self.config.max_price, price))

    def _penalty(self, base_price: float) -> float:
        total_bps = (
            self.config.half_spread_bps
            + self.config.slippage_bps
            + self.config.latency_bps
        )
        return base_price * (total_bps / 10_000.0)

    def entry_fill_price(
        self,
        direction: str,
        market_probability: float,
        pm_best_bid: Optional[float] = None,
        pm_best_ask: Optional[float] = None,
    ) -> float:
        """Return probability price paid for the chosen side."""
        if direction == "UP":
            base = pm_best_ask if pm_best_ask is not None else market_probability
        elif direction == "DOWN":
            if pm_best_bid is not None:
                # Buy NO by crossing YES bid -> NO ask ~= 1 - YES bid.
                base = 1.0 - pm_best_bid
            else:
                base = 1.0 - market_probability
        else:
            raise ValueError(f"unsupported direction: {direction}")

        base = self._clamp_price(float(base))
        return round(self._clamp_price(base + self._penalty(base)), 6)

    def entry_fee_rate(self, entry_price: float) -> float:
        if self.config.use_variable_fees:
            return polymarket_variable_fee_rate(entry_price)
        return max(0.0, float(self.config.entry_fee_rate))

    def exit_fee_rate(self, exit_price: float) -> float:
        if self.config.use_variable_fees:
            return polymarket_variable_fee_rate(exit_price)
        return max(0.0, float(self.config.exit_fee_rate))


class PaperTradingEngine:
    """Paper trading engine for binary event contracts (Polymarket-style)."""

    def __init__(
        self,
        starting_bankroll_usdc: float = 1000.0,
        fill_simulator: Optional[FillSimulator] = None,
        risk_manager: Optional[RiskManager] = None,
        risk_limits: Optional[PaperRiskLimits] = None,
    ):
        if starting_bankroll_usdc <= 0:
            raise ValueError("starting_bankroll_usdc must be > 0")
        self.starting_bankroll_usdc = float(starting_bankroll_usdc)
        self.cash_usdc = float(starting_bankroll_usdc)
        self.fill_simulator = fill_simulator or FillSimulator()
        self.risk_manager = risk_manager
        self.risk_limits = risk_limits or PaperRiskLimits()
        self.open_trades: dict[int, PaperTrade] = {}
        self.closed_trades: list[PaperTrade] = []
        self._next_trade_id = 1
        self._equity_curve: list[float] = [self.cash_usdc]
        self.last_reject_reason: str = ""
        self._daily_trade_counts: dict[str, int] = {}
        self._daily_realized_pnl: dict[str, float] = {}
        self._daily_start_equity: dict[str, float] = {}
        self._cooldown_until_epoch: Optional[float] = None
        self._cooldown_trigger_count: int = 0

    def _append_equity_point(self) -> None:
        self._equity_curve.append(round(self.cash_usdc, 6))

    @staticmethod
    def _contract_side(direction: str) -> str:
        return "YES" if direction == "UP" else "NO"

    def _ensure_day_tracking(self, day_key: str) -> None:
        if day_key not in self._daily_start_equity:
            self._daily_start_equity[day_key] = round(self.cash_usdc, 6)
        self._daily_trade_counts.setdefault(day_key, 0)
        self._daily_realized_pnl.setdefault(day_key, 0.0)

    def _daily_loss_stop_triggered(self, day_key: str) -> bool:
        frac = self.risk_limits.max_daily_loss_fraction
        if frac is None or frac <= 0:
            return False
        self._ensure_day_tracking(day_key)
        day_start = self._daily_start_equity[day_key]
        realized = self._daily_realized_pnl[day_key]
        if day_start <= 0:
            return False
        return (-realized) >= (day_start * float(frac))

    def _policy_reject_reason(self, signal: TradeSignal) -> str:
        ts = signal.timestamp or _utc_now_iso()
        try:
            ts_epoch = _parse_iso_to_epoch(ts)
        except Exception:
            ts_epoch = datetime.now(timezone.utc).timestamp()
        day_key = _utc_day_key_from_epoch(ts_epoch)
        self._ensure_day_tracking(day_key)

        if self._cooldown_until_epoch is not None and ts_epoch < self._cooldown_until_epoch:
            return "cooldown_active"
        if self._daily_loss_stop_triggered(day_key):
            return "daily_loss_stop"
        max_trades = self.risk_limits.max_trades_per_day
        if max_trades is not None and max_trades >= 0:
            if self._daily_trade_counts.get(day_key, 0) >= int(max_trades):
                return "max_trades_per_day"
        return ""

    def open_trade(
        self,
        signal: TradeSignal,
        event_id: str,
        pm_best_bid: Optional[float] = None,
        pm_best_ask: Optional[float] = None,
    ) -> Optional[PaperTrade]:
        """Open a paper trade from a validated signal. Returns None if skipped."""
        self.last_reject_reason = ""
        if signal.direction not in ("UP", "DOWN"):
            self.last_reject_reason = "direction_none"
            return None
        if not signal.risk_checks_passed:
            self.last_reject_reason = "signal_risk_checks_failed"
            return None
        if signal.suggested_size_usdc <= 0:
            self.last_reject_reason = "size_nonpositive"
            return None

        policy_reason = self._policy_reject_reason(signal)
        if policy_reason:
            self.last_reject_reason = policy_reason
            return None

        entry_price = self.fill_simulator.entry_fill_price(
            direction=signal.direction,
            market_probability=signal.market_probability,
            pm_best_bid=pm_best_bid,
            pm_best_ask=pm_best_ask,
        )
        if entry_price <= 0 or entry_price >= 1:
            self.last_reject_reason = "invalid_entry_price"
            return None

        entry_fee_rate = self.fill_simulator.entry_fee_rate(entry_price)
        total_cash_needed = signal.suggested_size_usdc * (1.0 + entry_fee_rate)
        if total_cash_needed > self.cash_usdc:
            self.last_reject_reason = "insufficient_cash"
            return None

        size_usdc = round(float(signal.suggested_size_usdc), 2)
        shares = round(size_usdc / entry_price, 8)
        entry_fee_usdc = round(size_usdc * entry_fee_rate, 6)

        trade = PaperTrade(
            trade_id=self._next_trade_id,
            event_id=event_id,
            opened_at=signal.timestamp or _utc_now_iso(),
            closed_at=None,
            status="OPEN",
            direction=signal.direction,
            contract_side=self._contract_side(signal.direction),
            entry_price=entry_price,
            exit_price=None,
            size_usdc=size_usdc,
            shares=shares,
            entry_fee_usdc=entry_fee_usdc,
            exit_fee_usdc=0.0,
            payout_usdc=0.0,
            pnl_usdc=None,
            return_pct=None,
            won=None,
            resolution_outcome_up=None,
            model_probability=float(signal.model_probability),
            market_probability_entry=float(signal.market_probability),
            ev_entry=float(signal.ev),
            reason=signal.reason or "",
        )
        self._next_trade_id += 1
        self.open_trades[trade.trade_id] = trade
        day_key = _utc_day_key_from_epoch(_parse_iso_to_epoch(trade.opened_at))
        self._ensure_day_tracking(day_key)
        self._daily_trade_counts[day_key] += 1
        self.cash_usdc = round(self.cash_usdc - size_usdc - entry_fee_usdc, 6)
        self._append_equity_point()
        return trade

    def resolve_trade(
        self,
        trade_id: int,
        outcome_up: bool,
        closed_at: Optional[str] = None,
    ) -> PaperTrade:
        """Resolve an open trade to settlement (binary 0/1 payout)."""
        if trade_id not in self.open_trades:
            raise KeyError(f"open trade not found: {trade_id}")

        trade = self.open_trades.pop(trade_id)
        if trade.contract_side == "YES":
            payout_per_share = 1.0 if outcome_up else 0.0
        else:
            payout_per_share = 0.0 if outcome_up else 1.0

        exit_price = 1.0 if payout_per_share > 0 else 0.0
        exit_fee_rate = self.fill_simulator.exit_fee_rate(exit_price)

        payout_usdc = round(trade.shares * payout_per_share, 6)
        exit_fee_usdc = round(payout_usdc * exit_fee_rate, 6)
        pnl_usdc = round(
            payout_usdc - exit_fee_usdc - trade.size_usdc - trade.entry_fee_usdc, 6
        )
        return_pct = round((pnl_usdc / trade.size_usdc) if trade.size_usdc > 0 else 0.0, 6)
        won = pnl_usdc > 0

        trade.closed_at = closed_at or _utc_now_iso()
        trade.status = "CLOSED"
        trade.exit_price = exit_price
        trade.exit_fee_usdc = exit_fee_usdc
        trade.payout_usdc = payout_usdc
        trade.pnl_usdc = pnl_usdc
        trade.return_pct = return_pct
        trade.won = won
        trade.resolution_outcome_up = bool(outcome_up)

        self.cash_usdc = round(self.cash_usdc + payout_usdc - exit_fee_usdc, 6)
        self.closed_trades.append(trade)
        self._append_equity_point()

        close_day_key = _utc_day_key_from_epoch(_parse_iso_to_epoch(trade.closed_at))
        self._ensure_day_tracking(close_day_key)
        self._daily_realized_pnl[close_day_key] = round(
            self._daily_realized_pnl.get(close_day_key, 0.0) + pnl_usdc,
            6,
        )

        # Engine-level cooldown tracks operational behavior in paper runs.
        if trade.won:
            if self.risk_manager is None:
                pass
        if self.risk_limits.cooldown_after_consecutive_losses and self.risk_limits.cooldown_minutes > 0:
            # Mirror consecutive-loss logic, independent of EV risk_manager wiring.
            losses_in_row = 0
            for prev in reversed(self.closed_trades):
                if prev.won is False:
                    losses_in_row += 1
                elif prev.won:
                    break
                else:
                    break
            threshold = int(self.risk_limits.cooldown_after_consecutive_losses)
            if losses_in_row >= threshold:
                close_ts_epoch = _parse_iso_to_epoch(trade.closed_at)
                cooldown_seconds = float(self.risk_limits.cooldown_minutes) * 60.0
                new_until = close_ts_epoch + cooldown_seconds
                if self._cooldown_until_epoch is None or new_until > self._cooldown_until_epoch:
                    self._cooldown_until_epoch = new_until
                    self._cooldown_trigger_count += 1

        if self.risk_manager is not None:
            actual = 1.0 if outcome_up else 0.0
            self.risk_manager.record_outcome(
                won=won,
                predicted_prob=trade.model_probability,
                actual=actual,
            )

        return trade

    @property
    def open_count(self) -> int:
        return len(self.open_trades)

    @property
    def closed_count(self) -> int:
        return len(self.closed_trades)

    def summary(self) -> dict:
        """Aggregate paper-trading stats for Phase 5 validation."""
        total_trades = len(self.closed_trades)
        total_pnl = round(sum(t.pnl_usdc or 0.0 for t in self.closed_trades), 6)
        wins = sum(1 for t in self.closed_trades if t.won)
        losses = sum(1 for t in self.closed_trades if t.won is False)
        win_rate = round((wins / total_trades) if total_trades else 0.0, 6)
        avg_pnl = round((total_pnl / total_trades) if total_trades else 0.0, 6)
        avg_return = round(
            (
                sum((t.return_pct or 0.0) for t in self.closed_trades) / total_trades
                if total_trades
                else 0.0
            ),
            6,
        )

        peak = self._equity_curve[0] if self._equity_curve else self.cash_usdc
        max_drawdown = 0.0
        for equity in self._equity_curve:
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > max_drawdown:
                    max_drawdown = dd

        return {
            "starting_bankroll_usdc": round(self.starting_bankroll_usdc, 6),
            "ending_bankroll_usdc": round(self.cash_usdc, 6),
            "open_trades": self.open_count,
            "closed_trades": self.closed_count,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_pnl_usdc": total_pnl,
            "avg_pnl_usdc": avg_pnl,
            "avg_return_pct": avg_return,
            "max_drawdown": round(max_drawdown, 6),
            "cooldown_triggers": self._cooldown_trigger_count,
            "daily_loss_stop_days": sum(
                1 for day in self._daily_start_equity if self._daily_loss_stop_triggered(day)
            ),
        }
