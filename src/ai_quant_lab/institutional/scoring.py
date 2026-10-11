from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from math import erf, isfinite, sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import BacktestResult, annualization_periods


class AdvancedPerformanceMetrics(BaseModel):
    """Risk, tail, capacity, and implementation metrics absent from headline PnL."""

    model_config = ConfigDict(frozen=True)

    calmar_ratio: float
    drawdown_duration_bars: int = Field(ge=0)
    tail_ratio: float = Field(ge=0)
    cvar_95_percent: float
    return_skewness: float
    turnover_per_bar: float = Field(ge=0)
    exposure_fraction: float = Field(ge=0, le=1)
    average_holding_bars: float = Field(ge=0)
    capacity_score: float = Field(ge=0, le=1)
    slippage_sensitivity: float = Field(ge=0)
    deflated_sharpe_ratio: float
    multiple_testing_adjusted_p_value: float = Field(ge=0, le=1)
    probability_of_backtest_overfitting: float = Field(ge=0, le=1)


class QuantScoreEvidence(BaseModel):
    """Independent robustness inputs used by the fixed institutional score."""

    model_config = ConfigDict(frozen=True)

    out_of_sample_stability: float = Field(ge=0, le=1)
    regime_robustness: float = Field(ge=0, le=1)
    parameter_stability: float = Field(ge=0, le=1)
    cost_robustness: float = Field(ge=0, le=1)
    statistical_significance: float = Field(ge=0, le=1)
    execution_feasibility: float = Field(ge=0, le=1)


class QuantScoreComponent(BaseModel):
    """One weighted, auditable score component."""

    model_config = ConfigDict(frozen=True)

    name: str
    weight: float = Field(gt=0, le=1)
    raw_score: float = Field(ge=0, le=100)
    weighted_score: float = Field(ge=0, le=100)


class QuantScore(BaseModel):
    """Fixed-weight candidate score; it is evidence, never trade authorization."""

    model_config = ConfigDict(frozen=True)

    total: float = Field(ge=0, le=100)
    components: tuple[QuantScoreComponent, ...]
    passes_research_threshold: bool
    threshold: float = Field(ge=0, le=100)
    live_trading_authorized: Literal[False] = False


def calculate_advanced_metrics(
    result: BacktestResult,
    *,
    trial_count: int,
    out_of_sample_stability: float,
    parameter_stability: float,
    baseline_cost_fraction: float,
    stressed_cost_fraction: float,
) -> AdvancedPerformanceMetrics:
    """Derive finite metrics from one immutable backtest and trial history."""

    equity = [point.equity for point in result.equity_curve]
    returns = [
        (current - previous) / previous for previous, current in pairwise(equity) if previous != 0
    ]
    negative_returns = sorted(value for value in returns if value < 0)
    positive_returns = sorted(value for value in returns if value > 0)
    lower_tail = _percentile(negative_returns or [0.0], 0.05)
    upper_tail = _percentile(positive_returns or [0.0], 0.95)
    tail_ratio = abs(upper_tail / lower_tail) if lower_tail < 0 else 0.0
    cvar_cutoff = _percentile(returns or [0.0], 0.05)
    cvar_sample = [value for value in returns if value <= cvar_cutoff]
    cvar = sum(cvar_sample) / len(cvar_sample) if cvar_sample else 0.0
    skewness = _skewness(returns)
    drawdown_duration = _maximum_drawdown_duration(equity)
    exposure = (
        sum(point.position != 0 for point in result.equity_curve) / len(result.equity_curve)
        if result.equity_curve
        else 0.0
    )
    average_holding = (
        sum(trade.bars_held for trade in result.trades) / len(result.trades)
        if result.trades
        else 0.0
    )
    turnover = len(result.trades) * 2 / max(1, len(result.equity_curve) - 1)
    trade_costs = sum(trade.costs for trade in result.trades)
    gross_magnitude = sum(abs(trade.gross_profit) for trade in result.trades)
    observed_cost_fraction = trade_costs / max(gross_magnitude, 1e-12)
    capacity_score = max(0.0, min(1.0, 1.0 - observed_cost_fraction))
    slippage_sensitivity = max(0.0, stressed_cost_fraction - baseline_cost_fraction)
    sharpe = result.metrics.sharpe_ratio
    observations = max(2, len(returns))
    expected_max_sharpe = sqrt(2.0 * max(0.0, _safe_log(max(1, trial_count))))
    deflated_sharpe = (sharpe - expected_max_sharpe) * sqrt((observations - 1) / observations)
    periods_per_year = annualization_periods(result.timeframe)
    test_statistic = sharpe * sqrt(observations / periods_per_year)
    naive_p_value = 1.0 - _normal_cdf(test_statistic)
    adjusted_p_value = bonferroni_adjusted_p_value(naive_p_value, trial_count)
    pbo = max(
        0.0,
        min(
            1.0,
            1.0
            - 0.45 * out_of_sample_stability
            - 0.35 * parameter_stability
            + 0.20 * min(1.0, _safe_log(max(1, trial_count)) / 8.0),
        ),
    )

    return AdvancedPerformanceMetrics(
        calmar_ratio=(
            result.metrics.net_return_percent / result.metrics.maximum_drawdown_percent
            if result.metrics.maximum_drawdown_percent > 0
            else max(0.0, result.metrics.net_return_percent)
        ),
        drawdown_duration_bars=drawdown_duration,
        tail_ratio=tail_ratio,
        cvar_95_percent=cvar * 100.0,
        return_skewness=skewness,
        turnover_per_bar=turnover,
        exposure_fraction=exposure,
        average_holding_bars=average_holding,
        capacity_score=capacity_score,
        slippage_sensitivity=slippage_sensitivity,
        deflated_sharpe_ratio=deflated_sharpe,
        multiple_testing_adjusted_p_value=adjusted_p_value,
        probability_of_backtest_overfitting=pbo,
    )


def bonferroni_adjusted_p_value(p_value: float, hypothesis_count: int) -> float:
    """Apply the family-wise Bonferroni correction with explicit clipping."""

    if hypothesis_count < 1:
        raise ValueError("Bonferroni hypothesis count must be at least one.")

    return min(1.0, max(0.0, p_value) * hypothesis_count)


def calculate_quant_score(
    result: BacktestResult,
    advanced: AdvancedPerformanceMetrics,
    evidence: QuantScoreEvidence,
    *,
    threshold: float = 60.0,
) -> QuantScore:
    """Apply the declared 20/15/15/15/10/10/10/5 score exactly once."""

    if not 0 <= threshold <= 100:
        raise ValueError("Quant Score threshold must be between zero and one hundred.")

    risk_adjusted = _clamp_score(
        50.0
        + result.metrics.sharpe_ratio * 12.0
        + result.metrics.sortino_ratio * 4.0
        + advanced.calmar_ratio * 5.0
    )
    drawdown_quality = _clamp_score(
        100.0
        - result.metrics.maximum_drawdown_percent * 3.0
        - min(30.0, advanced.drawdown_duration_bars / 10.0)
    )
    significance = _clamp_score(
        evidence.statistical_significance * 70.0
        + max(0.0, 1.0 - advanced.probability_of_backtest_overfitting) * 30.0
    )
    values = (
        ("risk_adjusted_return", 0.20, risk_adjusted),
        ("drawdown_quality", 0.15, drawdown_quality),
        ("out_of_sample_stability", 0.15, evidence.out_of_sample_stability * 100.0),
        ("regime_robustness", 0.15, evidence.regime_robustness * 100.0),
        ("parameter_stability", 0.10, evidence.parameter_stability * 100.0),
        ("cost_robustness", 0.10, evidence.cost_robustness * 100.0),
        ("statistical_significance", 0.10, significance),
        ("execution_feasibility", 0.05, evidence.execution_feasibility * 100.0),
    )
    components = tuple(
        QuantScoreComponent(
            name=name,
            weight=weight,
            raw_score=_clamp_score(raw_score),
            weighted_score=_clamp_score(raw_score) * weight,
        )
        for name, weight, raw_score in values
    )
    total = sum(component.weighted_score for component in components)

    return QuantScore(
        total=total,
        components=components,
        passes_research_threshold=total >= threshold,
        threshold=threshold,
    )


def _maximum_drawdown_duration(equity: Sequence[float]) -> int:
    peak = float("-inf")
    current_duration = 0
    maximum_duration = 0

    for value in equity:
        if value >= peak:
            peak = value
            current_duration = 0
        else:
            current_duration += 1
            maximum_duration = max(maximum_duration, current_duration)

    return maximum_duration


def _skewness(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0

    center = sum(values) / len(values)
    variance = sum((value - center) ** 2 for value in values) / len(values)

    if variance <= 0:
        return 0.0

    scale = sqrt(variance)

    return sum(((value - center) / scale) ** 3 for value in values) / len(values)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)

    return ordered[index]


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _safe_log(value: float) -> float:
    if value <= 0:
        return 0.0

    from math import log

    return log(value)


def _clamp_score(value: float) -> float:
    if not isfinite(value):
        return 0.0

    return max(0.0, min(100.0, value))
