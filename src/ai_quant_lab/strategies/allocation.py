from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import BacktestMetrics
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.regimes import MarketRegime


class StrategyCandidateScore(BaseModel):
    """Evidence and compatibility inputs for one immutable strategy version."""

    model_config = ConfigDict(frozen=True)

    strategy_version_id: str
    metrics: BacktestMetrics
    compatible_regimes: tuple[MarketRegime, ...]
    validation_passed: bool


class RankedStrategy(BaseModel):
    """One transparent allocator score and normalized shadow weight."""

    model_config = ConfigDict(frozen=True)

    strategy_version_id: str
    score: float
    shadow_weight: float = Field(ge=0, le=1)
    reason: str


class StrategyAllocation(BaseModel):
    """Research-only ranking; it cannot authorize broker execution."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    regime: MarketRegime
    champion_version_id: str | None
    rankings: tuple[RankedStrategy, ...]
    live_trading_authorized: Literal[False] = False


def allocate_strategies(
    *,
    pair: ForexPair,
    timeframe: Timeframe,
    regime: MarketRegime,
    candidates: tuple[StrategyCandidateScore, ...],
) -> StrategyAllocation:
    """Rank validated candidates using explicit performance and regime evidence."""

    unique_ids = {candidate.strategy_version_id for candidate in candidates}

    if len(unique_ids) != len(candidates):
        raise ValueError("Strategy allocator candidates must have unique version IDs.")

    scored: list[tuple[StrategyCandidateScore, float, str]] = []

    for candidate in candidates:
        metrics = candidate.metrics
        regime_match = regime in candidate.compatible_regimes

        if not candidate.validation_passed:
            score = 0.0
            reason = "Excluded because independent validation did not pass."
        else:
            score = max(
                0.0,
                50.0
                + metrics.net_return_percent
                + metrics.sharpe_ratio * 10.0
                + min(metrics.profit_factor, 5.0) * 5.0
                - metrics.maximum_drawdown_percent * 2.0
                + (20.0 if regime_match else -20.0),
            )
            reason = (
                "Validated; current regime is compatible."
                if regime_match
                else "Validated, but current regime is not in the evidence set."
            )

        scored.append((candidate, score, reason))

    total_score = sum(score for _, score, _ in scored)
    ordered = sorted(
        scored,
        key=lambda item: (-item[1], item[0].strategy_version_id),
    )
    rankings = tuple(
        RankedStrategy(
            strategy_version_id=candidate.strategy_version_id,
            score=score,
            shadow_weight=(score / total_score if total_score > 0 else 0.0),
            reason=reason,
        )
        for candidate, score, reason in ordered
    )
    champion = (
        rankings[0].strategy_version_id
        if rankings and rankings[0].score > 0
        else None
    )

    return StrategyAllocation(
        pair=pair,
        timeframe=timeframe,
        regime=regime,
        champion_version_id=champion,
        rankings=rankings,
    )
