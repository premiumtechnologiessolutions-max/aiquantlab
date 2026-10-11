from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskLimits(BaseModel):
    """Non-negotiable safety limits for research and simulated execution."""

    model_config = ConfigDict(frozen=True)

    maximum_risk_per_trade_percent: float = Field(default=1.0, gt=0, le=2.0)
    maximum_drawdown_percent: float = Field(default=20.0, gt=0, le=50.0)
    maximum_position_units: float = Field(default=100_000.0, gt=0)
    live_trading_allowed: Literal[False] = False


def calculate_position_units(
    *,
    account_equity: float,
    stop_distance_price: float,
    limits: RiskLimits | None = None,
) -> float:
    """Size a simulated position without exceeding the configured risk cap."""

    resolved_limits = limits or RiskLimits()

    if account_equity <= 0:
        raise ValueError("Account equity must be greater than zero.")

    if stop_distance_price <= 0:
        raise ValueError("Stop distance must be greater than zero.")

    risk_budget = account_equity * resolved_limits.maximum_risk_per_trade_percent / 100.0

    return min(
        risk_budget / stop_distance_price,
        resolved_limits.maximum_position_units,
    )


def assert_safe_mode(mode: str) -> None:
    """Reject any attempt to run this project in real-money live mode."""

    normalized = mode.strip().casefold()

    if normalized not in {"research", "shadow", "paper"}:
        raise ValueError(
            "Only research, shadow, and paper modes are permitted; "
            "real-money live trading is disabled.",
        )
