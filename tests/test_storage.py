from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore


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
        real_volume=None,
        spread_points=10,
    )


def test_parquet_round_trip(tmp_path: Path) -> None:
    store = ParquetMarketStore(tmp_path)

    bars = [
        make_bar(0),
        make_bar(15),
        make_bar(30),
    ]

    path = store.write_bars(bars)
    loaded_bars = store.read_bars("EURUSD", "M15")

    assert path.exists()
    assert loaded_bars == bars


def test_store_rejects_duplicate_bars(tmp_path: Path) -> None:
    store = ParquetMarketStore(tmp_path)

    bars = [
        make_bar(0),
        make_bar(0),
    ]

    with pytest.raises(ValueError, match="must be clean"):
        store.write_bars(bars)


def test_store_prevents_accidental_overwrite(
    tmp_path: Path,
) -> None:
    store = ParquetMarketStore(tmp_path)

    bars = [
        make_bar(0),
        make_bar(15),
    ]

    store.write_bars(bars)

    with pytest.raises(FileExistsError, match="already exists"):
        store.write_bars(bars)