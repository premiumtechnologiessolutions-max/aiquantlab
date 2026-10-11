from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from itertools import pairwise
from math import sqrt

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies.base import validate_strategy_bars


class MarketRegime(StrEnum):
    """Coarse, explainable market regimes used by the first MVP."""

    INSUFFICIENT_DATA = "insufficient_data"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"


class RegimePoint(BaseModel):
    """Regime classification and the observable statistics behind it."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    regime: MarketRegime
    return_over_window: float
    realized_volatility: float = Field(ge=0)


class RegimeChangePoint(BaseModel):
    """Causal change alert produced from adjacent trailing return windows."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    bar_index: int = Field(ge=0)
    standardized_score: float = Field(ge=0)
    direction: str


class RegimeSummary(BaseModel):
    """Aggregate distribution of regimes across one dataset."""

    model_config = ConfigDict(frozen=True)

    window: int = Field(ge=3)
    counts: dict[MarketRegime, int]
    dominant_regime: MarketRegime
    latest_regime: MarketRegime
    points: tuple[RegimePoint, ...]
    change_points: tuple[RegimeChangePoint, ...] = ()


def detect_market_regimes(
    bars: Sequence[MarketBar],
    *,
    window: int = 30,
    trend_threshold: float = 0.002,
    high_volatility_threshold: float = 0.0015,
) -> RegimeSummary:
    """Classify each bar using only trailing returns available at that time."""

    validate_strategy_bars(bars)

    if window < 3:
        raise ValueError("Regime window must contain at least three bars.")

    if trend_threshold <= 0 or high_volatility_threshold <= 0:
        raise ValueError("Regime thresholds must be greater than zero.")

    closes = deque[float]()
    points: list[RegimePoint] = []

    for bar in bars:
        closes.append(bar.close)

        if len(closes) > window:
            closes.popleft()

        if len(closes) < window:
            points.append(
                RegimePoint(
                    timestamp=bar.timestamp,
                    regime=MarketRegime.INSUFFICIENT_DATA,
                    return_over_window=0.0,
                    realized_volatility=0.0,
                )
            )
            continue

        values = tuple(closes)
        returns = tuple(
            (current - previous) / previous
            for previous, current in pairwise(values)
            if previous != 0
        )
        mean_return = sum(returns) / len(returns) if returns else 0.0
        volatility = (
            sqrt(
                sum((value - mean_return) ** 2 for value in returns)
                / len(returns)
            )
            if returns
            else 0.0
        )
        window_return = values[-1] / values[0] - 1.0

        if volatility >= high_volatility_threshold:
            regime = MarketRegime.HIGH_VOLATILITY
        elif window_return >= trend_threshold:
            regime = MarketRegime.TRENDING_UP
        elif window_return <= -trend_threshold:
            regime = MarketRegime.TRENDING_DOWN
        else:
            regime = MarketRegime.RANGING

        points.append(
            RegimePoint(
                timestamp=bar.timestamp,
                regime=regime,
                return_over_window=window_return,
                realized_volatility=volatility,
            )
        )

    counts: dict[MarketRegime, int] = {
        regime: sum(point.regime is regime for point in points)
        for regime in MarketRegime
    }
    eligible: dict[MarketRegime, int] = {
        regime: count
        for regime, count in counts.items()
        if regime is not MarketRegime.INSUFFICIENT_DATA
    }
    dominant = (
        min(
            eligible,
            key=lambda regime: (-eligible[regime], regime.value),
        )
        if eligible and max(eligible.values()) > 0
        else MarketRegime.INSUFFICIENT_DATA
    )

    return RegimeSummary(
        window=window,
        counts=counts,
        dominant_regime=dominant,
        latest_regime=points[-1].regime,
        points=tuple(points),
        change_points=detect_change_points(
            bars,
            window=max(3, window // 2),
        ),
    )


def detect_change_points(
    bars: Sequence[MarketBar],
    *,
    window: int = 20,
    threshold: float = 3.0,
) -> tuple[RegimeChangePoint, ...]:
    """Flag statistically large mean-return shifts without future observations."""

    validate_strategy_bars(bars)

    if window < 3:
        raise ValueError("Change-point window must contain at least three bars.")

    if threshold <= 0:
        raise ValueError("Change-point threshold must be greater than zero.")

    returns = [
        (bars[index].close - bars[index - 1].close) / bars[index - 1].close
        for index in range(1, len(bars))
    ]
    changes: list[RegimeChangePoint] = []
    last_alert_index = -window

    for return_index in range(window * 2, len(returns) + 1):
        previous = returns[return_index - window * 2 : return_index - window]
        recent = returns[return_index - window : return_index]
        previous_mean = sum(previous) / window
        recent_mean = sum(recent) / window
        combined = previous + recent
        combined_mean = sum(combined) / len(combined)
        standard_deviation = sqrt(
            sum((value - combined_mean) ** 2 for value in combined) / len(combined)
        )
        standard_error = standard_deviation * sqrt(2.0 / window)
        score = (
            abs(recent_mean - previous_mean) / standard_error
            if standard_error > 0
            else 0.0
        )
        bar_index = return_index

        if score < threshold or bar_index - last_alert_index < window:
            continue

        changes.append(
            RegimeChangePoint(
                timestamp=bars[bar_index].timestamp,
                bar_index=bar_index,
                standardized_score=score,
                direction=("up" if recent_mean > previous_mean else "down"),
            )
        )
        last_alert_index = bar_index

    return tuple(changes)
