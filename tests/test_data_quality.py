from datetime import UTC, datetime, timedelta

import pytest

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.quality import inspect_market_bars


def make_bar(
    minute: int,
    pair: ForexPair = "EURUSD",
    timeframe: Timeframe = "M15",
    *,
    base_time: datetime | None = None,
) -> MarketBar:
    if base_time is None:
        base_time = datetime(
            2026,
            7,
            28,
            tzinfo=UTC,
        )

    timestamp = base_time + timedelta(
        minutes=minute,
    )

    return MarketBar(
        pair=pair,
        timeframe=timeframe,
        timestamp=timestamp,
        open=1.1500,
        high=1.1520,
        low=1.1490,
        close=1.1510,
        tick_volume=1000,
        spread_points=10,
    )


def test_clean_market_bars() -> None:
    bars = [
        make_bar(0),
        make_bar(15),
        make_bar(30),
    ]

    report = inspect_market_bars(bars)

    assert report.bar_count == 3
    assert report.duplicate_timestamps == 0
    assert report.out_of_order_bars == 0
    assert report.missing_intervals == 0
    assert report.is_clean is True


def test_detects_missing_interval_during_market_hours() -> None:
    bars = [
        make_bar(0),
        make_bar(15),
        make_bar(45),
    ]

    report = inspect_market_bars(bars)

    assert report.missing_intervals == 1


def test_ignores_normal_weekend_market_closure() -> None:
    friday_time = datetime(
        2026,
        7,
        31,
        21,
        45,
        tzinfo=UTC,
    )

    sunday_time = datetime(
        2026,
        8,
        2,
        22,
        0,
        tzinfo=UTC,
    )

    bars = [
        make_bar(
            0,
            base_time=friday_time,
        ),
        make_bar(
            0,
            base_time=sunday_time,
        ),
    ]

    report = inspect_market_bars(bars)

    assert report.missing_intervals == 0
    assert report.is_clean is True


def test_detects_missing_bar_after_weekend_open() -> None:
    friday_time = datetime(
        2026,
        7,
        31,
        21,
        45,
        tzinfo=UTC,
    )

    sunday_time = datetime(
        2026,
        8,
        2,
        22,
        15,
        tzinfo=UTC,
    )

    bars = [
        make_bar(
            0,
            base_time=friday_time,
        ),
        make_bar(
            0,
            base_time=sunday_time,
        ),
    ]

    report = inspect_market_bars(bars)

    assert report.missing_intervals == 1


def test_detects_duplicate_and_out_of_order_bars() -> None:
    bars = [
        make_bar(0),
        make_bar(30),
        make_bar(15),
        make_bar(15),
    ]

    report = inspect_market_bars(bars)

    assert report.duplicate_timestamps == 1
    assert report.out_of_order_bars == 1
    assert report.is_clean is False


def test_rejects_mixed_currency_pairs() -> None:
    bars = [
        make_bar(
            0,
            pair="EURUSD",
        ),
        make_bar(
            15,
            pair="GBPUSD",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="same currency pair",
    ):
        inspect_market_bars(bars)


def test_rejects_mixed_timeframes() -> None:
    bars = [
        make_bar(
            0,
            timeframe="M15",
        ),
        make_bar(
            15,
            timeframe="H1",
        ),
    ]

    with pytest.raises(
        ValueError,
        match="same timeframe",
    ):
        inspect_market_bars(bars)


def test_rejects_empty_market_bar_sequence() -> None:
    with pytest.raises(
        ValueError,
        match="At least one market bar",
    ):
        inspect_market_bars([])