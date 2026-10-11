from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ai_quant_lab.data.models import MarketBar


def test_valid_market_bar_is_normalized_to_utc() -> None:
    beirut_time = timezone(timedelta(hours=3))

    bar = MarketBar(
        pair="EURUSD",
        timeframe="M15",
        timestamp=datetime(
            2026,
            8,
            1,
            10,
            0,
            tzinfo=beirut_time,
        ),
        open=1.1500,
        high=1.1520,
        low=1.1490,
        close=1.1510,
        tick_volume=1250,
        real_volume=None,
        spread_points=12,
    )

    assert bar.timestamp.tzinfo == UTC
    assert bar.timestamp.hour == 7


def test_market_bar_rejects_invalid_high() -> None:
    with pytest.raises(
        ValidationError,
        match="High must be",
    ):
        MarketBar(
            pair="EURUSD",
            timeframe="M15",
            timestamp=datetime.now(UTC),
            open=1.1500,
            high=1.1495,
            low=1.1480,
            close=1.1510,
            tick_volume=900,
            spread_points=10,
        )


def test_market_bar_rejects_naive_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="timezone",
    ):
        MarketBar(
            pair="GBPUSD",
            timeframe="H1",
            # Intentionally naive to verify timestamp validation.
            timestamp=datetime(  # noqa: DTZ001
                2026,
                8,
                1,
                10,
                0,
            ),
            open=1.3000,
            high=1.3050,
            low=1.2980,
            close=1.3020,
            tick_volume=1800,
            spread_points=15,
        )