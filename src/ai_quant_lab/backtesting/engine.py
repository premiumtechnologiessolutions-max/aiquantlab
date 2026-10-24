from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from math import sqrt

from ai_quant_lab.backtesting.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)
from ai_quant_lab.config import Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies import PositionSignal, ResearchStrategy
from ai_quant_lab.strategies.base import validate_strategy_bars


def run_backtest(
    bars: Sequence[MarketBar],
    strategy: ResearchStrategy,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a next-bar, cost-aware simulation with no look-ahead execution."""

    validate_strategy_bars(bars)

    if len(bars) < 2:
        raise ValueError("A backtest requires at least two market bars.")

    # XAUUSD requires explicit broker tick size and ounce exposure. The FX defaults\n    # (10,000 units and a 0.00001 point) are unsafe/misleading for gold.\n    if bars[0].pair == "XAUUSD" and (\n        config is None\n        or not {"quantity", "point_size"}.issubset(config.model_fields_set)\n    ):\n        raise ValueError(\n            "XAUUSD research requires explicit BacktestConfig quantity (troy ounces) "\n            "and point_size (broker price increment); verify contract economics."\n        )\n\n    resolved_config = config or BacktestConfig()\n    signals = strategy.generate_signals(bars)

    if len(signals) != len(bars):
        raise ValueError("A strategy must return exactly one signal per bar.")

    point_size = resolved_config.point_size or _default_point_size(bars[0].pair)
    equity = resolved_config.initial_capital
    position = PositionSignal.FLAT
    previous_close = bars[0].close
    trades: list[BacktestTrade] = []
    equity_curve = [
        EquityPoint(
            timestamp=bars[0].timestamp,
            equity=equity,
            position=position,
        )
    ]

    entry_price = 0.0
    entry_time = bars[0].timestamp
    entry_index = 0
    entry_cost = 0.0

    for index in range(1, len(bars)):
        bar = bars[index]

        equity += int(position) * resolved_config.quantity * (bar.open - previous_close)
        target = signals[index - 1]

        if target is not position:
            if position is not PositionSignal.FLAT:
                exit_cost = _execution_cost(bar.spread_points, point_size, resolved_config)
                equity -= exit_cost
                trades.append(
                    _build_trade(
                        direction=position,
                        entry_time=entry_time,
                        exit_time=bar.timestamp,
                        entry_price=entry_price,
                        exit_price=bar.open,
                        entry_index=entry_index,
                        exit_index=index,
                        entry_cost=entry_cost,
                        exit_cost=exit_cost,
                        config=resolved_config,
                    )
                )

            position = target

            if position is not PositionSignal.FLAT:
                entry_cost = _execution_cost(bar.spread_points, point_size, resolved_config)
                equity -= entry_cost
                entry_price = bar.open
                entry_time = bar.timestamp
                entry_index = index

        equity += int(position) * resolved_config.quantity * (bar.close - bar.open)
        previous_close = bar.close

        equity_curve.append(
            EquityPoint(
                timestamp=bar.timestamp,
                equity=equity,
                position=position,
            )
        )

    if position is not PositionSignal.FLAT:
        final_bar = bars[-1]
        exit_cost = _execution_cost(final_bar.spread_points, point_size, resolved_config)
        equity -= exit_cost
        trades.append(
            _build_trade(
                direction=position,
                entry_time=entry_time,
                exit_time=final_bar.timestamp,
                entry_price=entry_price,
                exit_price=final_bar.close,
                entry_index=entry_index,
                exit_index=len(bars) - 1,
                entry_cost=entry_cost,
                exit_cost=exit_cost,
                config=resolved_config,
            )
        )
        equity_curve[-1] = EquityPoint(
            timestamp=final_bar.timestamp,
            equity=equity,
            position=PositionSignal.FLAT,
        )

    metrics = _calculate_metrics(
        initial_capital=resolved_config.initial_capital,
        ending_equity=equity,
        trades=trades,
        equity_curve=equity_curve,
        periods_per_year=annualization_periods(bars[0].timeframe),
    )

    return BacktestResult(
        pair=bars[0].pair,
        timeframe=bars[0].timeframe,
        strategy=strategy.descriptor,
        config=resolved_config,
        started_at=bars[0].timestamp,
        ended_at=bars[-1].timestamp,
        metrics=metrics,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
    )


def annualization_periods(timeframe: Timeframe) -> int:
    """Return the declared FX bar count used to annualize risk metrics.

    The laboratory treats one trading year as 252 twenty-four-hour FX sessions.
    Intraday Sharpe and Sortino ratios therefore scale by the number of bars in
    those sessions instead of applying the daily-only ``sqrt(252)`` factor to
    every timeframe.
    """

    periods: dict[Timeframe, int] = {
        "M1": 252 * 24 * 60,
        "M5": 252 * 24 * 12,
        "M15": 252 * 24 * 4,
        "H1": 252 * 24,
        "H4": 252 * 6,
        "D1": 252,
    }

    return periods[timeframe]


def _default_point_size(pair: str) -> float:
    """Return the conventional broker point size for five/three-digit FX."""

    if pair == "XAUUSD":\n        # A broker-specific value is mandatory through BacktestConfig; this\n        # fallback prevents accidental use of the FX five-decimal convention.\n        return 0.01\n    return 0.001 if pair.endswith("JPY") else 0.00001


def _execution_cost(
    spread_points: float,
    point_size: float,
    config: BacktestConfig,
) -> float:
    """Calculate the cost charged on one entry or exit side."""

    price_cost = (
        spread_points * point_size / 2.0
        + config.slippage_points * point_size
    )

    return config.quantity * price_cost + config.commission_per_side


def _build_trade(
    *,
    direction: PositionSignal,
    entry_time: object,
    exit_time: object,
    entry_price: float,
    exit_price: float,
    entry_index: int,
    exit_index: int,
    entry_cost: float,
    exit_cost: float,
    config: BacktestConfig,
) -> BacktestTrade:
    """Create one validated closed trade from execution state."""

    from datetime import datetime

    if not isinstance(entry_time, datetime) or not isinstance(exit_time, datetime):
        raise TypeError("Trade timestamps must be datetime values.")

    gross_profit = int(direction) * config.quantity * (exit_price - entry_price)
    costs = entry_cost + exit_cost

    return BacktestTrade(
        direction=direction,
        entry_time=entry_time,
        exit_time=exit_time,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=config.quantity,
        gross_profit=gross_profit,
        costs=costs,
        net_profit=gross_profit - costs,
        bars_held=max(1, exit_index - entry_index),
    )


def _calculate_metrics(
    *,
    initial_capital: float,
    ending_equity: float,
    trades: Sequence[BacktestTrade],
    equity_curve: Sequence[EquityPoint],
    periods_per_year: int,
) -> BacktestMetrics:
    """Calculate finite, deterministic performance metrics."""

    net_profit = ending_equity - initial_capital
    returns = [
        (current.equity - previous.equity) / previous.equity
        for previous, current in pairwise(equity_curve)
        if previous.equity != 0
    ]

    mean_return = sum(returns) / len(returns) if returns else 0.0
    variance = (
        sum((value - mean_return) ** 2 for value in returns) / len(returns)
        if returns
        else 0.0
    )
    standard_deviation = sqrt(variance)
    downside = [min(0.0, value) for value in returns]
    downside_deviation = (
        sqrt(sum(value**2 for value in downside) / len(downside))
        if downside
        else 0.0
    )

    peak = equity_curve[0].equity
    maximum_drawdown = 0.0

    for point in equity_curve:
        peak = max(peak, point.equity)

        if peak > 0:
            maximum_drawdown = max(
                maximum_drawdown,
                (peak - point.equity) / peak * 100.0,
            )

    profits = [trade.net_profit for trade in trades if trade.net_profit > 0]
    losses = [-trade.net_profit for trade in trades if trade.net_profit < 0]
    gross_profit = sum(profits)
    gross_loss = sum(losses)
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else (gross_profit if gross_profit > 0 else 0.0)
    )

    return BacktestMetrics(
        net_profit=net_profit,
        net_return_percent=net_profit / initial_capital * 100.0,
        maximum_drawdown_percent=maximum_drawdown,
        sharpe_ratio=(
            mean_return / standard_deviation * sqrt(periods_per_year)
            if standard_deviation
            else 0.0
        ),
        sortino_ratio=(
            mean_return / downside_deviation * sqrt(periods_per_year)
            if downside_deviation
            else 0.0
        ),
        profit_factor=profit_factor,
        expected_value=(net_profit / len(trades) if trades else 0.0),
        win_rate_percent=(len(profits) / len(trades) * 100.0 if trades else 0.0),
        trade_count=len(trades),
    )
