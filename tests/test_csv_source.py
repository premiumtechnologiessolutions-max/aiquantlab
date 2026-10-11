from datetime import UTC, datetime
from pathlib import Path

import pytest

from ai_quant_lab.data.csv_source import CsvMarketDataSource


def write_csv(
    path: Path,
    content: str,
) -> None:
    path.write_text(
        content.strip() + "\n",
        encoding="utf-8",
    )


def test_csv_source_reads_market_bars(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "eurusd.csv"

    write_csv(
        csv_path,
        """
timestamp,open,high,low,close,tick_volume,spread_points,real_volume
2026-08-01T00:00:00+00:00,1.1500,1.1520,1.1490,1.1510,1000,10,
2026-08-01T00:15:00+00:00,1.1510,1.1530,1.1500,1.1520,1100,11,250
2026-08-01T00:30:00+00:00,1.1520,1.1540,1.1510,1.1530,1200,9,
        """,
    )

    source = CsvMarketDataSource(
        csv_path,
        source_name="broker-export",
    )

    bars = source.fetch_bars(
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

    assert source.name == "broker-export"
    assert len(bars) == 3
    assert bars[0].pair == "EURUSD"
    assert bars[0].timeframe == "M15"
    assert bars[0].timestamp.tzinfo == UTC
    assert bars[1].real_volume == 250.0


def test_csv_source_filters_requested_interval(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "eurusd.csv"

    write_csv(
        csv_path,
        """
timestamp,open,high,low,close,tick_volume,spread_points
2026-08-01T00:00:00+00:00,1.1500,1.1520,1.1490,1.1510,1000,10
2026-08-01T00:15:00+00:00,1.1510,1.1530,1.1500,1.1520,1100,11
2026-08-01T00:30:00+00:00,1.1520,1.1540,1.1510,1.1530,1200,9
        """,
    )

    source = CsvMarketDataSource(csv_path)

    bars = source.fetch_bars(
        pair="EURUSD",
        timeframe="M15",
        start=datetime(
            2026,
            8,
            1,
            0,
            15,
            tzinfo=UTC,
        ),
        end=datetime(
            2026,
            8,
            1,
            0,
            30,
            tzinfo=UTC,
        ),
    )

    assert len(bars) == 1
    assert bars[0].timestamp.minute == 15


def test_csv_source_rejects_missing_columns(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "invalid.csv"

    write_csv(
        csv_path,
        """
timestamp,open,high,low,close,tick_volume
2026-08-01T00:00:00+00:00,1.1500,1.1520,1.1490,1.1510,1000
        """,
    )

    source = CsvMarketDataSource(csv_path)

    with pytest.raises(
        ValueError,
        match="missing required columns",
    ):
        source.fetch_bars(
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


def test_csv_source_rejects_naive_timestamp(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "invalid-time.csv"

    write_csv(
        csv_path,
        """
timestamp,open,high,low,close,tick_volume,spread_points
2026-08-01T00:00:00,1.1500,1.1520,1.1490,1.1510,1000,10
        """,
    )

    source = CsvMarketDataSource(csv_path)

    with pytest.raises(
        ValueError,
        match="include timezone",
    ):
        source.fetch_bars(
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