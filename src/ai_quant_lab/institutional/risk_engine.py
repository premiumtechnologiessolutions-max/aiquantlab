from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PositionDirection(StrEnum):
    """Normalized direction used by portfolio exposure accounting."""

    BUY = "buy"
    SELL = "sell"


class PositionRiskInput(BaseModel):
    """Sanitized position input; credentials and account identifiers are excluded."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=6)
    direction: PositionDirection
    notional_usd: float = Field(gt=0)
    cluster: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = "".join(character for character in value.upper() if character.isalpha())
        if len(normalized) < 6:
            raise ValueError("A risk symbol must contain at least six currency letters.")
        return normalized[:6]


class PortfolioRiskLimits(BaseModel):
    """Hard portfolio limits owned by Aegis."""

    model_config = ConfigDict(frozen=True)

    maximum_gross_leverage: float = Field(default=2.0, gt=0)
    maximum_single_asset_fraction: float = Field(default=0.35, gt=0, le=1)
    maximum_currency_exposure_fraction: float = Field(default=0.60, gt=0)
    maximum_cluster_fraction: float = Field(default=0.60, gt=0)
    maximum_correlated_bets: int = Field(default=3, ge=1)
    maximum_cvar_95_fraction: float = Field(default=0.03, gt=0, le=1)


class PortfolioRiskSnapshot(BaseModel):
    """Auditable portfolio-level exposure and tail-risk decision."""

    model_config = ConfigDict(frozen=True)

    equity_usd: float = Field(gt=0)
    position_count: int = Field(ge=0)
    gross_notional_usd: float = Field(ge=0)
    gross_leverage: float = Field(ge=0)
    largest_asset_fraction: float = Field(ge=0, le=1)
    maximum_currency_exposure_fraction: float = Field(ge=0)
    currency_exposure_usd: dict[str, float]
    cluster_exposure_usd: dict[str, float]
    correlated_bet_count: int = Field(ge=0)
    portfolio_cvar_95_fraction: float = Field(le=0)
    scenario_count: int = Field(ge=0)
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    allows_new_risk: bool
    size_multiplier: float = Field(ge=0, le=1)
    live_trading_authorized: Literal[False] = False


def evaluate_portfolio_risk(
    positions: Sequence[PositionRiskInput],
    *,
    equity_usd: float,
    scenario_returns: Sequence[float] = (),
    limits: PortfolioRiskLimits | None = None,
) -> PortfolioRiskSnapshot:
    """Evaluate leverage, concentration, currency clusters, correlation, and CVaR."""

    if equity_usd <= 0:
        raise ValueError("Portfolio equity must be positive.")

    policy = limits or PortfolioRiskLimits()
    gross_notional = sum(position.notional_usd for position in positions)
    gross_leverage = gross_notional / equity_usd
    largest_asset_fraction = (
        max((position.notional_usd for position in positions), default=0.0) / equity_usd
    )
    currency_exposure: defaultdict[str, float] = defaultdict(float)
    cluster_exposure: defaultdict[str, float] = defaultdict(float)
    usd_directions: list[int] = []

    for position in positions:
        base = position.symbol[:3]
        quote = position.symbol[3:6]
        sign = 1 if position.direction is PositionDirection.BUY else -1
        currency_exposure[base] += sign * position.notional_usd
        currency_exposure[quote] -= sign * position.notional_usd
        cluster = position.cluster or _default_cluster(base, quote)
        cluster_exposure[cluster] += position.notional_usd

        if base == "USD":
            usd_directions.append(sign)
        elif quote == "USD":
            usd_directions.append(-sign)

    maximum_currency_fraction = max(
        (abs(value) / equity_usd for value in currency_exposure.values()),
        default=0.0,
    )
    maximum_cluster_fraction = max(
        (value / max(gross_notional, 1e-12) for value in cluster_exposure.values()),
        default=0.0,
    )
    direction_counts = Counter(usd_directions)
    correlated_bet_count = max(direction_counts.values(), default=0)
    cvar = _cvar_95(scenario_returns)
    blockers: list[str] = []
    warnings: list[str] = []

    if gross_leverage > policy.maximum_gross_leverage:
        blockers.append("Aggregate gross leverage exceeded the portfolio hard limit.")
    if largest_asset_fraction > policy.maximum_single_asset_fraction and len(positions) > 1:
        blockers.append("A single asset exceeded the portfolio concentration limit.")
    if maximum_currency_fraction > policy.maximum_currency_exposure_fraction:
        blockers.append("Net currency exposure exceeded its risk budget.")
    if maximum_cluster_fraction > policy.maximum_cluster_fraction and len(positions) > 1:
        blockers.append("One correlated cluster exceeded its portfolio risk budget.")
    if correlated_bet_count > policy.maximum_correlated_bets:
        blockers.append("Too many positions express the same directional USD bet.")
    if scenario_returns and abs(cvar) > policy.maximum_cvar_95_fraction:
        blockers.append("Portfolio CVaR exceeded the configured tail-risk limit.")
    if not scenario_returns:
        warnings.append("Portfolio CVaR was unavailable because no aligned scenarios were supplied.")

    size_multiplier = 0.0 if blockers else (0.75 if warnings and positions else 1.0)

    return PortfolioRiskSnapshot(
        equity_usd=equity_usd,
        position_count=len(positions),
        gross_notional_usd=gross_notional,
        gross_leverage=gross_leverage,
        largest_asset_fraction=largest_asset_fraction,
        maximum_currency_exposure_fraction=maximum_currency_fraction,
        currency_exposure_usd=dict(sorted(currency_exposure.items())),
        cluster_exposure_usd=dict(sorted(cluster_exposure.items())),
        correlated_bet_count=correlated_bet_count,
        portfolio_cvar_95_fraction=cvar,
        scenario_count=len(scenario_returns),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        allows_new_risk=not blockers,
        size_multiplier=size_multiplier,
    )


def _default_cluster(base: str, quote: str) -> str:
    if base == "USD":
        return f"{quote.lower()}_fx"
    if quote == "USD":
        return f"{base.lower()}_fx"
    return f"{base.lower()}_{quote.lower()}_cross"


def _cvar_95(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0

    ordered = sorted(returns)
    tail_count = max(1, round(len(ordered) * 0.05))
    tail = ordered[:tail_count]
    return min(0.0, sum(tail) / len(tail))
