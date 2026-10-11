from __future__ import annotations

from collections.abc import Sequence
from enum import IntEnum, StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.data.models import MarketBar


class PositionSignal(IntEnum):
    """Target market position emitted by a research strategy."""

    SHORT = -1
    FLAT = 0
    LONG = 1


class StrategyFamily(StrEnum):
    """High-level deterministic strategy families supported by the lab."""

    TREND = "trend"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    VOLATILITY = "volatility"
    ADAPTIVE = "adaptive"
    STATISTICAL = "statistical"
    BASELINE = "baseline"


class StrategyDescriptor(BaseModel):
    """Serializable identity and parameters of one strategy instance."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    family: StrategyFamily
    parameters: dict[str, int | float | str] = Field(default_factory=dict)


class ResearchStrategy(Protocol):
    """Interface implemented by deterministic research strategies."""

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible strategy description."""

        ...  # pragma: no cover

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate one target-position signal per market bar."""

        ...  # pragma: no cover


def validate_strategy_bars(
    bars: Sequence[MarketBar],
) -> None:
    """Reject mixed or non-chronological inputs before signal generation."""

    if not bars:
        raise ValueError("A strategy requires at least one market bar.")

    first = bars[0]

    if any(bar.pair != first.pair or bar.timeframe != first.timeframe for bar in bars):
        raise ValueError("Strategy bars must use one pair and one timeframe.")

    timestamps = [bar.timestamp for bar in bars]

    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("Strategy bars must be unique and chronological.")
