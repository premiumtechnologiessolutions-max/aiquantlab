from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.ingestion import ingest_market_data
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore


class FakeMarketDataSource:
    """Controlled source used only for automated tests."""

    name = "fake-source"

    def __init__(
        self,
        bars: Sequence[MarketBar],
    ) -> None:
        self._bars = bars

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        return self._bars


def make_bar(minute: int) -> MarketBar:
    timestamp = datetime(
        2026,
        8,
        1,
        tzinfo=UTC,
    ) + timedelta(minutes=minute)

    return MarketBar(
        pair="EURUSD",
        timeframe="M15",
        timestamp=timestamp,
        open=1.1500,
        high=1.1520,
        low=1.1490,
        close=1.1510,
        tick_volume=1000,
        spread_points=10,
    )


def test_ingestion_pipeline_writes_dataset_and_manifest(
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

    result = ingest_market_data(
        source=source,
        store=store,
        pair="EURUSD",
        timeframe="M15",
        start=datetime(
            2026,
            8,
            1,
            tzinfo=UTC,
        ),
        end=datetime(
            2026,
            8,
            1,
            1,
            tzinfo=UTC,
        ),
    )

    assert result.source == "fake-source"
    assert result.bars_written == 3
    assert result.missing_intervals == 0
    assert result.dataset_path.exists()
    assert result.manifest_path.exists()
    assert len(result.dataset_sha256) == 64


def test_ingestion_rejects_empty_source(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource([])
    store = ParquetMarketStore(tmp_path)

    with pytest.raises(ValueError, match="returned no bars"):
        ingest_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                8,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                8,
                1,
                1,
                tzinfo=UTC,
            ),
        )


def test_ingestion_rejects_bar_outside_requested_interval(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource(
        [
            make_bar(0),
            make_bar(75),
        ]
    )

    store = ParquetMarketStore(tmp_path)

    with pytest.raises(ValueError, match="outside"):
        ingest_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            start=datetime(
                2026,
                8,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2026,
                8,
                1,
                1,
                tzinfo=UTC,
            ),
        )


def test_ingestion_rejects_naive_time_boundary(
    tmp_path: Path,
) -> None:
    source = FakeMarketDataSource([make_bar(0)])
    store = ParquetMarketStore(tmp_path)

    with pytest.raises(ValueError, match="timezone"):
        ingest_market_data(
            source=source,
            store=store,
            pair="EURUSD",
            timeframe="M15",
            # Intentionally naive to verify boundary validation.
            start=datetime(2026, 8, 1),  # noqa: DTZ001
            end=datetime(
                2026,
                8,
                1,
                1,
                tzinfo=UTC,
            ),
        )