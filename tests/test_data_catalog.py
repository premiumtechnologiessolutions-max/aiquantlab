from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_quant_lab.data.catalog import (
    build_dataset_manifest,
    write_dataset_manifest,
)
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
        spread_points=10,
    )


def test_build_dataset_manifest(tmp_path: Path) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(0),
            make_bar(15),
            make_bar(30),
        ]
    )

    manifest = build_dataset_manifest(
        store,
        "EURUSD",
        "M15",
    )

    assert manifest.schema_version == "1.0"
    assert manifest.bar_count == 3
    assert manifest.missing_intervals == 0
    assert manifest.file_size_bytes > 0
    assert len(manifest.sha256) == 64
    assert manifest.relative_path == "EURUSD/M15/bars.parquet"


def test_write_dataset_manifest(tmp_path: Path) -> None:
    store = ParquetMarketStore(tmp_path)

    store.write_bars(
        [
            make_bar(0),
            make_bar(15),
        ]
    )

    manifest = build_dataset_manifest(
        store,
        "EURUSD",
        "M15",
    )

    path = write_dataset_manifest(
        manifest,
        root=tmp_path,
    )

    content = path.read_text(encoding="utf-8")

    assert path.exists()
    assert '"pair":"EURUSD"' in content.replace(" ", "")
    assert manifest.sha256 in content