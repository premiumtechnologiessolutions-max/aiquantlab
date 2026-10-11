from datetime import UTC, datetime, timedelta

import pytest

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.merge import (
    ConflictingMarketBarError,
    merge_market_bars,
)
from ai_quant_lab.data.models import MarketBar


def make_bar(
    minute: int,
    *,
    pair: ForexPair = "EURUSD",
    timeframe: Timeframe = "M15",
    close_price: float = 1.1510,
) -> MarketBar:
    """Create one controlled market bar for merge tests."""

    open_price = 1.1500

    timestamp = datetime(
        2026,
        7,
        28,
        tzinfo=UTC,
    ) + timedelta(minutes=minute)

    return MarketBar(
        pair=pair,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_price,
        high=max(
            open_price,
            close_price,
        )
        + 0.0010,
        low=min(
            open_price,
            close_price,
        )
        - 0.0010,
        close=close_price,
        tick_volume=1000 + minute,
        real_volume=None,
        spread_points=10,
    )


def test_merge_combines_and_sorts_market_bars() -> None:
    existing_bars = [
        make_bar(30),
        make_bar(0),
    ]

    incoming_bars = [
        make_bar(45),
        make_bar(15),
    ]

    merged_bars = merge_market_bars(
        existing_bars,
        incoming_bars,
    )

    assert len(merged_bars) == 4

    assert [
        bar.timestamp.minute
        for bar in merged_bars
    ] == [
        0,
        15,
        30,
        45,
    ]


def test_merge_removes_identical_overlapping_bar() -> None:
    existing_bars = [
        make_bar(0),
        make_bar(15),
    ]

    incoming_bars = [
        make_bar(15),
        make_bar(30),
    ]

    merged_bars = merge_market_bars(
        existing_bars,
        incoming_bars,
    )

    assert len(merged_bars) == 3

    assert [
        bar.timestamp.minute
        for bar in merged_bars
    ] == [
        0,
        15,
        30,
    ]


def test_merge_rejects_conflicting_overlapping_bar() -> None:
    existing_bars = [
        make_bar(
            15,
            close_price=1.1510,
        ),
    ]

    incoming_bars = [
        make_bar(
            15,
            close_price=1.1520,
        ),
    ]

    with pytest.raises(
        ConflictingMarketBarError,
        match="Conflicting market bars",
    ):
        merge_market_bars(
            existing_bars,
            incoming_bars,
        )


def test_merge_rejects_mixed_currency_pairs() -> None:
    existing_bars = [
        make_bar(
            0,
            pair="EURUSD",
        ),
    ]

    incoming_bars = [
        make_bar(
            15,
            pair="GBPUSD",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="same currency pair",
    ):
        merge_market_bars(
            existing_bars,
            incoming_bars,
        )


def test_merge_rejects_mixed_timeframes() -> None:
    existing_bars = [
        make_bar(
            0,
            timeframe="M15",
        ),
    ]

    incoming_bars = [
        make_bar(
            15,
            timeframe="H1",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="same timeframe",
    ):
        merge_market_bars(
            existing_bars,
            incoming_bars,
        )


def test_merge_accepts_only_incoming_bars() -> None:
    incoming_bars = [
        make_bar(30),
        make_bar(0),
        make_bar(15),
    ]

    merged_bars = merge_market_bars(
        [],
        incoming_bars,
    )

    assert len(merged_bars) == 3
    assert merged_bars[0].timestamp.minute == 0
    assert merged_bars[-1].timestamp.minute == 30


def test_merge_rejects_two_empty_sequences() -> None:
    with pytest.raises(
        ValueError,
        match="At least one existing or incoming",
    ):
        merge_market_bars(
            [],
            [],
        )