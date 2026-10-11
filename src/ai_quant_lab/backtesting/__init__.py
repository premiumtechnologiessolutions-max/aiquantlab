"""Causal, transaction-cost-aware research backtesting."""

from ai_quant_lab.backtesting.engine import annualization_periods, run_backtest
from ai_quant_lab.backtesting.models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTrade,
    EquityPoint,
)

__all__ = [
    "annualization_periods",
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestResult",
    "BacktestTrade",
    "EquityPoint",
    "run_backtest",
]
