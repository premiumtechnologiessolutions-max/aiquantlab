from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.quality import inspect_market_bars


class ConflictingMarketBarError(ValueError):
    """Raised when two different market bars share one timestamp."""


def merge_market_bars(
    existing_bars: Sequence[MarketBar],
    incoming_bars: Sequence[MarketBar],
) -> list[MarketBar]:
    """Merge two compatible market-bar sequences safely.

    Identical overlapping bars are stored once. Different bars sharing
    the same timestamp are rejected to preserve dataset reproducibility.
    """

    combined_bars = [
        *existing_bars,
        *incoming_bars,
    ]

    if not combined_bars:
        raise ValueError(
            "At least one existing or incoming market bar is required.",
        )

    expected_pair = combined_bars[0].pair
    expected_timeframe = combined_bars[0].timeframe

    bars_by_timestamp: dict[datetime, MarketBar] = {}

    for bar in combined_bars:
        if bar.pair != expected_pair:
            raise ValueError(
                "All merged bars must belong to the same currency pair.",
            )

        if bar.timeframe != expected_timeframe:
            raise ValueError(
                "All merged bars must use the same timeframe.",
            )

        stored_bar = bars_by_timestamp.get(
            bar.timestamp,
        )

        if stored_bar is None:
            bars_by_timestamp[bar.timestamp] = bar
            continue

        if stored_bar != bar:
            raise ConflictingMarketBarError(
                "Conflicting market bars found at timestamp "
                f"{bar.timestamp.isoformat()}.",
            )

    merged_bars = sorted(
        bars_by_timestamp.values(),
        key=lambda bar: bar.timestamp,
    )

    quality_report = inspect_market_bars(
        merged_bars,
    )

    if not quality_report.is_clean:
        raise RuntimeError(
            "Merged market bars failed structural quality validation.",
        )

    return merged_bars