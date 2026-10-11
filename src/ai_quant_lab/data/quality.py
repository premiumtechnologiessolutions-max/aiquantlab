from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from itertools import pairwise
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.trading_calendar import ForexTradingCalendar

TIMEFRAME_SECONDS: Final[dict[Timeframe, int]] = {
    "M1": 60,
    "M5": 5 * 60,
    "M15": 15 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
    "D1": 24 * 60 * 60,
}


class DataQualityReport(BaseModel):
    """Quality report for a sequence of canonical market bars."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    bar_count: int = Field(gt=0)

    first_timestamp: datetime
    last_timestamp: datetime

    duplicate_timestamps: int = Field(ge=0)
    out_of_order_bars: int = Field(ge=0)
    missing_intervals: int = Field(ge=0)

    @property
    def is_clean(self) -> bool:
        """Return whether the dataset passes structural checks."""

        return (
            self.duplicate_timestamps == 0
            and self.out_of_order_bars == 0
        )


def inspect_market_bars(
    bars: Sequence[MarketBar],
    *,
    trading_calendar: ForexTradingCalendar | None = None,
) -> DataQualityReport:
    """Inspect market bars using the FX weekly trading calendar."""

    if not bars:
        raise ValueError("At least one market bar is required.")

    expected_pair = bars[0].pair
    expected_timeframe = bars[0].timeframe

    timestamps: list[datetime] = []

    for bar in bars:
        if bar.pair != expected_pair:
            raise ValueError(
                "All bars must belong to the same currency pair.",
            )

        if bar.timeframe != expected_timeframe:
            raise ValueError(
                "All bars must use the same timeframe.",
            )

        timestamps.append(bar.timestamp)

    duplicate_timestamps = (
        len(timestamps)
        - len(set(timestamps))
    )

    out_of_order_bars = sum(
        current < previous
        for previous, current in pairwise(timestamps)
    )

    expected_seconds = TIMEFRAME_SECONDS[
        expected_timeframe
    ]

    calendar = (
        trading_calendar
        if trading_calendar is not None
        else ForexTradingCalendar()
    )

    sorted_unique_timestamps = sorted(
        set(timestamps),
    )

    missing_intervals = sum(
        calendar.count_missing_bar_openings(
            previous=previous,
            current=current,
            interval_seconds=expected_seconds,
        )
        for previous, current in pairwise(
            sorted_unique_timestamps,
        )
    )

    return DataQualityReport(
        pair=expected_pair,
        timeframe=expected_timeframe,
        bar_count=len(bars),
        first_timestamp=min(timestamps),
        last_timestamp=max(timestamps),
        duplicate_timestamps=duplicate_timestamps,
        out_of_order_bars=out_of_order_bars,
        missing_intervals=missing_intervals,
    )
