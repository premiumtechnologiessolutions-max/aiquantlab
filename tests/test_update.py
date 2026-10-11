from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.merge import ConflictingMarketBarError
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.data.update import update_market_data


class FakeMarketDataSource:
    """Controlled market-data source used by update tests."""

    name = "fake-update-source"

    def __init__(
        self,
        bars: Sequence[MarketBar],
    ) -> None:
        self._bars = list(bars)

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        return self._bars


def make_bar(
    minute: int,
    *,
    pair: ForexPair = "EURUSD",
    timeframe: Timeframe = "M15",
    close_price: float = 1.1510,
) -> MarketBar:
    """Create one controlled market bar."""

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


def test_update_creates_new_dataset(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource(
        [
            make_bar(0),
            make_bar(15),
            make_bar(30),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    result = update_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=datetime(
            2026,
            7,
            28,
            tzinfo=UTC,
        ),
        end=datetime(
            2026,
            7,
            28,
            1,
            tzinfo=UTC,
        ),
    )

    assert result.source == "fake-update-source"
    assert result.existing_bars == 0
    assert result.fetched_bars == 3
    assert result.overlapping_bars == 0
    assert result.new_bars == 3
    assert result.total_bars == 3
    assert result.dataset_path.exists()
    assert result.manifest_path.exists()
    assert len(result.dataset_sha256) == 64


def test_update_merges_overlapping_and_new_bars(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(0),
            make_bar(15),
            make_bar(30),
        ]
    )

    source = FakeMarketDataSource(
        [
            make_bar(15),
            make_bar(30),
            make_bar(45),
        ]
    )

    result = update_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=datetime(
            2026,
            7,
            28,
            tzinfo=UTC,
        ),
        end=datetime(
            2026,
            7,
            28,
            1,
            tzinfo=UTC,
        ),
    )

    loaded_bars = store.read_bars(
        "EURUSD",
        "M15",
    )

    assert result.existing_bars == 3
    assert result.fetched_bars == 3
    assert result.overlapping_bars == 2
    assert result.new_bars == 1
    assert result.total_bars == 4

    assert [
        bar.timestamp.minute
        for bar in loaded_bars
    ] == [
        0,
        15,
        30,
        45,
    ]


def test_update_accepts_batch_with_no_new_bars(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    existing_bars = [
        make_bar(0),
        make_bar(15),
    ]

    store.write_bars(existing_bars)

    source = FakeMarketDataSource(existing_bars)

    result = update_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=datetime(
            2026,
            7,
            28,
            tzinfo=UTC,
        ),
        end=datetime(
            2026,
            7,
            28,
            1,
            tzinfo=UTC,
        ),
    )

    assert result.overlapping_bars == 2
    assert result.new_bars == 0
    assert result.total_bars == 2


def test_update_rejects_conflicting_overlap(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(
                15,
                close_price=1.1510,
            ),
        ]
    )

    source = FakeMarketDataSource(
        [
            make_bar(
                15,
                close_price=1.1520,
            ),
        ]
    )

    with pytest.raises(
        ConflictingMarketBarError,
        match="Conflicting market bars",
    ):
        update_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                7,
                28,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                7,
                28,
                1,
                tzinfo=UTC,
            ),
        )


def test_update_rejects_empty_source(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource([])
    store = ParquetMarketStore(tmp_path)

    with pytest.raises(
        ValueError,
        match="returned no bars",
    ):
        update_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                7,
                28,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                7,
                28,
                1,
                tzinfo=UTC,
            ),
        )


def test_update_rejects_bar_outside_requested_interval(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource(
        [
            make_bar(0),
            make_bar(75),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    with pytest.raises(
        ValueError,
        match="outside",
    ):
        update_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                7,
                28,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                7,
                28,
                1,
                tzinfo=UTC,
            ),
        )


def test_update_rejects_wrong_currency_pair(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource(
        [
            make_bar(
                0,
                pair="GBPUSD",
            ),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    with pytest.raises(
        ValueError,
        match="different currency pair",
    ):
        update_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                7,
                28,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                7,
                28,
                1,
                tzinfo=UTC,
            ),
        )


def test_update_rejects_naive_time_boundary(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource(
        [
            make_bar(0),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    with pytest.raises(
        ValueError,
        match="timezone information",
    ):
        update_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            # Intentionally naive to verify validation.
            start=datetime(2026, 7, 28),  # noqa: DTZ001
            end=datetime(
                2026,
                7,
                28,
                1,
                tzinfo=UTC,
            ),
        )