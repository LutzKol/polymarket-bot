"""Trade signal dataclass for Phase 4 EV-Engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class TradeSignal:
    timestamp: str
    direction: str  # "UP" / "DOWN" / "NONE"
    model_probability: float
    market_probability: float
    ev: float
    kelly_fraction: float  # raw Kelly (uncapped)
    suggested_size_usdc: float  # capped at max_fraction * bankroll
    risk_checks_passed: bool
    reason: str  # "" or e.g. "oracle_stale;brier_gate_exceeded"
    bankroll_usdc: float
    brier_score: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def csv_columns() -> list[str]:
        return [
            "timestamp",
            "direction",
            "model_probability",
            "market_probability",
            "ev",
            "kelly_fraction",
            "suggested_size_usdc",
            "risk_checks_passed",
            "reason",
            "bankroll_usdc",
            "brier_score",
        ]
