"""EV-Engine: Model prediction → EV calculation → Kelly sizing → Risk checks."""

from __future__ import annotations

import json
import math
import pickle
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from phase2_pipeline.trade_signal import TradeSignal


class ModelLoader:
    """Load a logistic regression model and predict P(UP)."""

    def __init__(self, model_path: str, feature_columns: list[str] | None = None):
        self._model = None
        self._weights: Optional[list[float]] = None

        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._weights = [float(w) for w in data["weights"]]
            # Prefer feature_columns embedded in the model file
            if "feature_columns" in data and not feature_columns:
                feature_columns = data["feature_columns"]
        elif suffix in (".pkl", ".joblib"):
            with path.open("rb") as f:
                self._model = pickle.load(f)
        else:
            raise ValueError(f"Unsupported model format: {suffix}")

        if not feature_columns:
            raise ValueError("feature_columns must be provided or embedded in model file")
        self.feature_columns = feature_columns

    def predict_proba(self, features: dict) -> Optional[float]:
        """Return P(UP) given a feature dict, or None if features are missing."""
        values = []
        for col in self.feature_columns:
            val = features.get(col)
            if val is None:
                return None
            values.append(float(val))

        if self._weights is not None:
            bias = self._weights[0]
            weights = self._weights[1:]
            if len(weights) != len(values):
                return None
            z = bias + sum(w * x for w, x in zip(weights, values))
            return 1.0 / (1.0 + math.exp(-z))

        # sklearn-compatible model
        prob = self._model.predict_proba([values])
        return float(prob[0][1])


class EVCalculator:
    """Calculate expected value and trade direction."""

    def __init__(self, ev_threshold: float = 0.02, fee: float = 0.02):
        self.ev_threshold = ev_threshold
        self.fee = fee

    def calculate(
        self,
        model_prob: float,
        market_prob: float,
        cost_yes: float | None = None,
        cost_no: float | None = None,
    ) -> tuple[float, str]:
        """Return (ev, direction). Direction is 'NONE' if EV < threshold.

        When cost_yes / cost_no are provided (from orderbook best ask / 1-best_bid),
        EV is calculated against the actual entry cost rather than the mid probability.
        This prevents entering trades where the spread destroys the edge.
        """
        price_yes = cost_yes if cost_yes is not None else market_prob
        price_no = cost_no if cost_no is not None else (1 - market_prob)

        ev_yes = model_prob * (1 - self.fee) - price_yes
        ev_no = (1 - model_prob) * (1 - self.fee) - price_no

        if ev_yes >= ev_no:
            best_ev = ev_yes
            direction = "UP"
        else:
            best_ev = ev_no
            direction = "DOWN"

        if best_ev < self.ev_threshold:
            return best_ev, "NONE"

        return best_ev, direction

    def calculate_limit_order(
        self,
        model_prob: float,
        edge_buffer: float = 0.0,
    ) -> tuple[float, str, float]:
        """Compute limit price that meets EV threshold for a limit order.

        Returns (ev, direction, limit_price).
        Direction is 'NONE' if no viable limit price exists.
        """
        # YES side: limit_yes = model_prob * (1 - fee) - ev_threshold - edge_buffer
        limit_yes = model_prob * (1 - self.fee) - self.ev_threshold - edge_buffer
        # NO side: limit_no = (1 - model_prob) * (1 - fee) - ev_threshold - edge_buffer
        limit_no = (1 - model_prob) * (1 - self.fee) - self.ev_threshold - edge_buffer

        # EV at the limit price equals ev_threshold + edge_buffer by construction
        ev_yes = model_prob * (1 - self.fee) - limit_yes if limit_yes > 0 else -1.0
        ev_no = (1 - model_prob) * (1 - self.fee) - limit_no if limit_no > 0 else -1.0

        if ev_yes >= ev_no and limit_yes > 0 and limit_yes < 1:
            return round(ev_yes, 6), "UP", round(limit_yes, 4)
        elif limit_no > 0 and limit_no < 1:
            return round(ev_no, 6), "DOWN", round(limit_no, 4)

        return 0.0, "NONE", 0.0


class KellySizer:
    """Kelly criterion position sizing with a hard cap."""

    def __init__(self, max_fraction: float = 0.02):
        self.max_fraction = max_fraction

    def size(
        self,
        model_prob: float,
        market_prob: float,
        direction: str,
        bankroll: float,
        fee: float = 0.02,
        cost_override: float | None = None,
    ) -> tuple[float, float]:
        """Return (kelly_fraction, size_usdc). Returns (0, 0) for no edge.

        When cost_override is provided (e.g. a limit price), it replaces the
        market_prob-derived cost for Kelly sizing.
        """
        if direction == "NONE" or bankroll <= 0:
            return 0.0, 0.0

        if direction == "UP":
            p = model_prob
            cost = market_prob
        else:
            p = 1.0 - model_prob
            cost = 1.0 - market_prob

        if cost_override is not None:
            cost = cost_override

        if cost <= 0 or cost >= 1:
            return 0.0, 0.0

        b = ((1 - fee) / cost) - 1
        if b <= 0:
            return 0.0, 0.0

        q = 1.0 - p
        kelly = (p * b - q) / b

        if kelly <= 0:
            return 0.0, 0.0

        capped = min(kelly, self.max_fraction)
        size_usdc = round(capped * bankroll, 2)
        return kelly, size_usdc


class RiskManager:
    """Kill-switch checks per CRITICAL_RULES.md."""

    def __init__(
        self,
        max_consecutive_losses: int = 3,
        brier_gate: float = 0.24,
        max_fraction: float = 0.02,
    ):
        self.max_consecutive_losses = max_consecutive_losses
        self.brier_gate = brier_gate
        self.max_fraction = max_fraction
        self.consecutive_losses = 0
        self._brier_scores: deque[float] = deque(maxlen=100)

    @property
    def rolling_brier(self) -> Optional[float]:
        if not self._brier_scores:
            return None
        return sum(self._brier_scores) / len(self._brier_scores)

    def record_outcome(self, won: bool, predicted_prob: float, actual: float) -> None:
        """Record a trade outcome for Brier tracking."""
        brier = (predicted_prob - actual) ** 2
        self._brier_scores.append(brier)
        if won:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    def check_all(
        self,
        model_output: Optional[float],
        oracle_stale: bool,
        size_usdc: float,
        bankroll: float,
    ) -> tuple[bool, str]:
        """Return (passed, reason). reason is semicolon-separated failure list."""
        reasons: list[str] = []

        if model_output is None:
            reasons.append("model_output_none")

        if oracle_stale:
            reasons.append("oracle_stale")

        if self.consecutive_losses >= self.max_consecutive_losses:
            reasons.append("consecutive_losses")

        rb = self.rolling_brier
        if rb is not None and rb > self.brier_gate:
            reasons.append("brier_gate_exceeded")

        if bankroll > 0 and (size_usdc / bankroll) > self.max_fraction:
            reasons.append("size_exceeds_max_fraction")

        passed = len(reasons) == 0
        return passed, ";".join(reasons)


def evaluate_signal(
    features: dict,
    model: ModelLoader,
    market_prob: float,
    bankroll: float,
    risk_manager: RiskManager,
    ev_calculator: EVCalculator,
    kelly_sizer: KellySizer,
    oracle_stale: bool = False,
    cost_yes: float | None = None,
    cost_no: float | None = None,
    limit_order_mode: bool = False,
    limit_edge_buffer: float = 0.0,
) -> TradeSignal:
    """Top-level convenience: features → TradeSignal.

    When limit_order_mode is True, computes a limit price where the EV meets
    threshold and sizes via Kelly at that limit price instead of market mid.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    model_prob = model.predict_proba(features)
    limit_price: float | None = None

    if model_prob is not None:
        if limit_order_mode:
            ev, direction, limit_price = ev_calculator.calculate_limit_order(
                model_prob, edge_buffer=limit_edge_buffer,
            )
            if direction != "NONE" and limit_price is not None and limit_price > 0:
                kelly_frac, size_usdc = kelly_sizer.size(
                    model_prob, market_prob, direction, bankroll,
                    ev_calculator.fee, cost_override=limit_price,
                )
            else:
                kelly_frac, size_usdc = 0.0, 0.0
        else:
            ev, direction = ev_calculator.calculate(
                model_prob, market_prob, cost_yes=cost_yes, cost_no=cost_no,
            )
            kelly_frac, size_usdc = kelly_sizer.size(
                model_prob, market_prob, direction, bankroll, ev_calculator.fee
            )
    else:
        ev, direction = 0.0, "NONE"
        kelly_frac, size_usdc = 0.0, 0.0

    passed, reason = risk_manager.check_all(model_prob, oracle_stale, size_usdc, bankroll)

    return TradeSignal(
        timestamp=ts,
        direction=direction,
        model_probability=model_prob if model_prob is not None else 0.0,
        market_probability=market_prob,
        ev=ev,
        kelly_fraction=kelly_frac,
        suggested_size_usdc=size_usdc,
        risk_checks_passed=passed,
        reason=reason,
        bankroll_usdc=bankroll,
        brier_score=risk_manager.rolling_brier,
        limit_price=limit_price if limit_order_mode else None,
    )
