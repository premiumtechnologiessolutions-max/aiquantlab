from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.backfill import (
    backfill_market_data,
    build_backfill_intervals,
)
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore


class FakeHistoricalSource:
    """Controlled historical source used by backfill tests."""

    name = "fake-historical-source"

    def __init__(
        self,
        bars: Sequence[MarketBar],
    ) -> None:
        self._bars = list(bars)

        self.fetch_calls: list[
            tuple[
                ForexPair,
                Timeframe,
                datetime,
                datetime,
            ]
        ] = []

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        self.fetch_calls.append(
            (
                pair,
                timeframe,
                start,
                end,
            )
        )

        return [
            bar
            for bar in self._bars
            if (
                bar.pair == pair
                and bar.timeframe == timeframe
                and start <= bar.timestamp < end
            )
        ]


def utc_datetime(
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    """Create one UTC datetime during July 2026."""

    return datetime(
        2026,
        7,
        day,
        hour,
        minute,
        tzinfo=UTC,
    )


def make_bar(
    day: int,
    hour: int = 0,
    minute: int = 0,
    *,
    pair: ForexPair = "EURUSD",
    timeframe: Timeframe = "M15",
) -> MarketBar:
    """Create one controlled market bar for backfill tests."""

    timestamp = utc_datetime(
        day,
        hour,
        minute,
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
        real_volume=None,
        spread_points=10,
    )


def test_build_backfill_intervals_splits_requested_range() -> None:
    intervals = build_backfill_intervals(
        start=utc_datetime(1),
        end=utc_datetime(6),
        chunk_days=2,
    )

    assert intervals == [
        (
            utc_datetime(1),
            utc_datetime(3),
        ),
        (
            utc_datetime(3),
            utc_datetime(5),
        ),
        (
            utc_datetime(5),
            utc_datetime(6),
        ),
    ]


def test_build_backfill_intervals_normalizes_to_utc() -> None:
    local_timezone = timezone(
        timedelta(hours=3),
    )

    intervals = build_backfill_intervals(
        start=datetime(
            2026,
            7,
            1,
            tzinfo=local_timezone,
        ),
        end=datetime(
            2026,
            7,
            3,
            tzinfo=local_timezone,
        ),
        chunk_days=1,
    )

    assert intervals[0][0] == datetime(
        2026,
        6,
        30,
        21,
        tzinfo=UTC,
    )

    assert intervals[-1][1] == datetime(
        2026,
        7,
        2,
        21,
        tzinfo=UTC,
    )


def test_backfill_creates_dataset_across_multiple_chunks(
    tmp_path: Path,
) -> None:
    source = FakeHistoricalSource(
        [
            make_bar(1),
            make_bar(1, 0, 15),
            make_bar(3),
            make_bar(4),
            make_bar(5),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    result = backfill_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=utc_datetime(1),
        end=utc_datetime(6),
        chunk_days=2,
    )

    stored_bars = store.read_bars(
        "EURUSD",
        "M15",
    )

    assert result.source == "fake-historical-source"
    assert result.chunks_total == 3
    assert result.chunks_updated == 3
    assert result.chunks_empty == 0
    assert result.initial_bars == 0
    assert result.fetched_bars == 5
    assert result.new_bars == 5
    assert result.final_bars == 5
    assert len(stored_bars) == 5
    assert result.dataset_path.exists()
    assert result.manifest_path.exists()
    assert len(result.dataset_sha256) == 64


def test_backfill_records_empty_chunks(
    tmp_path: Path,
) -> None:
    source = FakeHistoricalSource(
        [
            make_bar(1),
            make_bar(5),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    result = backfill_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=utc_datetime(1),
        end=utc_datetime(7),
        chunk_days=2,
    )

    assert result.chunks_total == 3
    assert result.chunks_updated == 2
    assert result.chunks_empty == 1
    assert result.fetched_bars == 2
    assert result.final_bars == 2

    assert [
        chunk.status
        for chunk in result.chunks
    ] == [
        "updated",
        "empty",
        "updated",
    ]


def test_backfill_merges_with_existing_dataset(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(1),
            make_bar(2),
        ]
    )

    source = FakeHistoricalSource(
        [
            make_bar(2),
            make_bar(3),
            make_bar(4),
        ]
    )

    result = backfill_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=utc_datetime(2),
        end=utc_datetime(5),
        chunk_days=1,
    )

    stored_bars = store.read_bars(
        "EURUSD",
        "M15",
    )

    assert result.initial_bars == 2
    assert result.fetched_bars == 3
    assert result.new_bars == 2
    assert result.final_bars == 4

    assert [
        bar.timestamp.day
        for bar in stored_bars
    ] == [
        1,
        2,
        3,
        4,
    ]


def test_backfill_preserves_existing_dataset_when_chunks_are_empty(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(1),
            make_bar(1, 0, 15),
        ]
    )

    source = FakeHistoricalSource([])

    result = backfill_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=utc_datetime(2),
        end=utc_datetime(4),
        chunk_days=1,
    )

    assert result.initial_bars == 2
    assert result.fetched_bars == 0
    assert result.new_bars == 0
    assert result.final_bars == 2
    assert result.chunks_updated == 0
    assert result.chunks_empty == 2


def test_backfill_calls_source_for_every_chunk(
    tmp_path: Path,
) -> None:
    source = FakeHistoricalSource(
        [
            make_bar(1),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    backfill_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=utc_datetime(1),
        end=utc_datetime(4),
        chunk_days=1,
    )

    assert source.fetch_calls == [
        (
            "EURUSD",
            "M15",
            utc_datetime(1),
            utc_datetime(2),
        ),
        (
            "EURUSD",
            "M15",
            utc_datetime(2),
            utc_datetime(3),
        ),
        (
            "EURUSD",
            "M15",
            utc_datetime(3),
            utc_datetime(4),
        ),
    ]


def test_backfill_rejects_all_empty_chunks_without_dataset(
    tmp_path: Path,
) -> None:
    source = FakeHistoricalSource([])
    store = ParquetMarketStore(tmp_path)

    with pytest.raises(
        ValueError,
        match="without any market bars",
    ):
        backfill_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=utc_datetime(1),
            end=utc_datetime(4),
            chunk_days=1,
        )


def test_build_backfill_intervals_rejects_invalid_chunk_days() -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        build_backfill_intervals(
            start=utc_datetime(1),
            end=utc_datetime(2),
            chunk_days=0,
        )


def test_build_backfill_intervals_rejects_invalid_range() -> None:
    boundary = utc_datetime(1)

    with pytest.raises(
        ValueError,
        match="earlier than end",
    ):
        build_backfill_intervals(
            start=boundary,
            end=boundary,
            chunk_days=1,
        )


def test_build_backfill_intervals_rejects_naive_boundary() -> None:
    with pytest.raises(
        ValueError,
        match="timezone information",
    ):
        build_backfill_intervals(
            # Intentionally naive to verify validation.
            start=datetime(2026, 7, 1),  # noqa: DTZ001
            end=utc_datetime(2),
            chunk_days=1,
        )