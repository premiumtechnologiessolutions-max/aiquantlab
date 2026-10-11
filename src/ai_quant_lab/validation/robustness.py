from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from random import Random

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    run_backtest,
)
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies import ResearchStrategy
from ai_quant_lab.validation.gates import ValidationPolicy, validate_backtest


class MonteCarloSummary(BaseModel):
    """Distribution of bootstrapped net results from closed simulated trades."""

    model_config = ConfigDict(frozen=True)

    simulations: int = Field(ge=1)
    seed: int
    probability_of_profit: float = Field(ge=0, le=1)
    fifth_percentile_profit: float
    median_profit: float
    ninety_fifth_percentile_profit: float


class WalkForwardWindow(BaseModel):
    """One chronological out-of-sample window and its observed metrics."""

    model_config = ConfigDict(frozen=True)

    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    purge_bars: int = Field(default=0, ge=0)
    metrics: BacktestMetrics
    passed: bool


class WalkForwardSummary(BaseModel):
    """Aggregate evidence across expanding chronological test windows."""

    model_config = ConfigDict(frozen=True)

    windows: tuple[WalkForwardWindow, ...]
    pass_fraction: float = Field(ge=0, le=1)
    passed: bool


class ParameterVariantResult(BaseModel):
    """Observed result for one neighboring strategy parameter set."""

    model_config = ConfigDict(frozen=True)

    strategy_name: str
    parameters: dict[str, int | float | str]
    net_return_percent: float
    maximum_drawdown_percent: float = Field(ge=0)
    profitable: bool


class ParameterStabilitySummary(BaseModel):
    """Robustness of a strategy family across neighboring parameter choices."""

    model_config = ConfigDict(frozen=True)

    variants: tuple[ParameterVariantResult, ...]
    profitable_fraction: float = Field(ge=0, le=1)
    return_range_percent: float = Field(ge=0)
    passed: bool


def chronological_splits(
    item_count: int,
    *,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> tuple[tuple[range, range], ...]:
    """Build expanding chronological train/test windows for walk-forward work."""

    if item_count <= 0:
        raise ValueError("Item count must be greater than zero.")

    if train_size <= 0 or test_size <= 0:
        raise ValueError("Train and test sizes must be greater than zero.")

    resolved_step = step_size or test_size

    if resolved_step <= 0:
        raise ValueError("Step size must be greater than zero.")

    splits: list[tuple[range, range]] = []
    train_end = train_size

    while train_end + test_size <= item_count:
        splits.append(
            (
                range(train_end),
                range(train_end, train_end + test_size),
            )
        )
        train_end += resolved_step

    return tuple(splits)


def purged_chronological_splits(
    item_count: int,
    *,
    train_size: int,
    test_size: int,
    purge_size: int = 1,
    step_size: int | None = None,
) -> tuple[tuple[range, range], ...]:
    """Build expanding train/test windows separated by a leakage-control gap."""

    if purge_size < 0:
        raise ValueError("Purge size cannot be negative.")

    if item_count <= 0 or train_size <= 0 or test_size <= 0:
        raise ValueError("Item, train, and test sizes must be greater than zero.")

    resolved_step = step_size or test_size

    if resolved_step <= 0:
        raise ValueError("Step size must be greater than zero.")

    splits: list[tuple[range, range]] = []
    train_end = train_size

    while train_end + purge_size + test_size <= item_count:
        test_start = train_end + purge_size
        splits.append((range(train_end), range(test_start, test_start + test_size)))
        train_end += resolved_step

    return tuple(splits)


def monte_carlo_trade_profits(
    trades: Sequence[BacktestTrade],
    *,
    simulations: int = 1_000,
    seed: int = 7,
) -> MonteCarloSummary:
    """Bootstrap closed trade outcomes with a deterministic random seed."""

    if not trades:
        raise ValueError("Monte Carlo analysis requires at least one closed trade.")

    if simulations < 1:
        raise ValueError("Monte Carlo simulations must be at least one.")

    random = Random(seed)
    profits = [trade.net_profit for trade in trades]
    outcomes = sorted(sum(random.choice(profits) for _ in profits) for _ in range(simulations))

    return MonteCarloSummary(
        simulations=simulations,
        seed=seed,
        probability_of_profit=sum(value > 0 for value in outcomes) / simulations,
        fifth_percentile_profit=_percentile(outcomes, 0.05),
        median_profit=_percentile(outcomes, 0.50),
        ninety_fifth_percentile_profit=_percentile(outcomes, 0.95),
    )


def run_walk_forward_validation(
    bars: Sequence[MarketBar],
    *,
    strategy_factory: Callable[[], ResearchStrategy],
    train_size: int,
    test_size: int,
    step_size: int | None = None,
    purge_bars: int = 1,
    backtest_config: BacktestConfig | None = None,
    validation_policy: ValidationPolicy | None = None,
    minimum_pass_fraction: float = 0.6,
) -> WalkForwardSummary:
    """Run fixed rules on chronological test windows separated by a purge gap."""

    if not 0 <= minimum_pass_fraction <= 1:
        raise ValueError("Minimum pass fraction must be between zero and one.")

    splits = purged_chronological_splits(
        len(bars),
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        purge_size=purge_bars,
    )

    if not splits:
        raise ValueError("The dataset is too short for the requested walk-forward windows.")

    windows: list[WalkForwardWindow] = []

    for train_range, test_range in splits:
        test_bars = tuple(bars[index] for index in test_range)

        if len(test_bars) < 2:
            raise ValueError("Each walk-forward test window requires at least two bars.")

        result = run_backtest(test_bars, strategy_factory(), backtest_config)
        validation = validate_backtest(result, validation_policy)
        windows.append(
            WalkForwardWindow(
                train_start=bars[train_range.start].timestamp,
                train_end=bars[train_range.stop - 1].timestamp,
                test_start=test_bars[0].timestamp,
                test_end=test_bars[-1].timestamp,
                purge_bars=purge_bars,
                metrics=result.metrics,
                passed=validation.passed_quantitative_gates,
            )
        )

    pass_fraction = sum(window.passed for window in windows) / len(windows)

    return WalkForwardSummary(
        windows=tuple(windows),
        pass_fraction=pass_fraction,
        passed=pass_fraction >= minimum_pass_fraction,
    )


def assess_parameter_stability(
    results: Sequence[BacktestResult],
    *,
    minimum_profitable_fraction: float = 0.6,
    maximum_return_range_percent: float = 50.0,
) -> ParameterStabilitySummary:
    """Evaluate neighboring immutable parameter variants without cherry-picking."""

    if not results:
        raise ValueError("Parameter stability requires at least one backtest result.")

    if not 0 <= minimum_profitable_fraction <= 1:
        raise ValueError("Minimum profitable fraction must be between zero and one.")

    if maximum_return_range_percent < 0:
        raise ValueError("Maximum return range must be non-negative.")

    variants = tuple(
        ParameterVariantResult(
            strategy_name=result.strategy.name,
            parameters=result.strategy.parameters,
            net_return_percent=result.metrics.net_return_percent,
            maximum_drawdown_percent=result.metrics.maximum_drawdown_percent,
            profitable=result.metrics.net_profit > 0,
        )
        for result in results
    )
    profitable_fraction = sum(item.profitable for item in variants) / len(variants)
    returns = [item.net_return_percent for item in variants]
    return_range = max(returns) - min(returns)

    return ParameterStabilitySummary(
        variants=variants,
        profitable_fraction=profitable_fraction,
        return_range_percent=return_range,
        passed=(
            profitable_fraction >= minimum_profitable_fraction
            and return_range <= maximum_return_range_percent
        ),
    )


def _percentile(
    values: Sequence[float],
    fraction: float,
) -> float:
    """Return a nearest-rank percentile for an already sorted sequence."""

    index = round((len(values) - 1) * fraction)

    return values[index]
