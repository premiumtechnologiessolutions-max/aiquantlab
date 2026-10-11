from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.strategies import PositionSignal, StrategyDescriptor


class BacktestConfig(BaseModel):
    """Execution and cost assumptions for a reproducible backtest."""

    model_config = ConfigDict(frozen=True)

    initial_capital: float = Field(default=10_000.0, gt=0)
    quantity: float = Field(default=10_000.0, gt=0)
    slippage_points: float = Field(default=1.0, ge=0)
    commission_per_side: float = Field(default=0.0, ge=0)
    point_size: float | None = Field(default=None, gt=0)


class BacktestTrade(BaseModel):
    """One closed simulated trade including all modeled costs."""

    model_config = ConfigDict(frozen=True)

    direction: PositionSignal
    entry_time: datetime
    exit_time: datetime
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    gross_profit: float
    costs: float = Field(ge=0)
    net_profit: float
    bars_held: int = Field(ge=1)

    @field_validator("direction")
    @classmethod
    def direction_must_be_open(
        cls,
        value: PositionSignal,
    ) -> PositionSignal:
        """A closed trade cannot have a flat direction."""

        if value is PositionSignal.FLAT:
            raise ValueError("A trade direction must be long or short.")

        return value


class EquityPoint(BaseModel):
    """One marked-to-market account value in the equity curve."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    equity: float
    position: PositionSignal


class BacktestMetrics(BaseModel):
    """Core performance and stability metrics for a simulated strategy."""

    model_config = ConfigDict(frozen=True)

    net_profit: float
    net_return_percent: float
    maximum_drawdown_percent: float = Field(ge=0)
    sharpe_ratio: float
    sortino_ratio: float
    profit_factor: float
    expected_value: float
    win_rate_percent: float = Field(ge=0, le=100)
    trade_count: int = Field(ge=0)


class BacktestResult(BaseModel):
    """Complete immutable result of one deterministic backtest."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    strategy: StrategyDescriptor
    config: BacktestConfig
    started_at: datetime
    ended_at: datetime
    metrics: BacktestMetrics
    trades: tuple[BacktestTrade, ...]
    equity_curve: tuple[EquityPoint, ...]
    signal_lag_bars: int = 1
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
