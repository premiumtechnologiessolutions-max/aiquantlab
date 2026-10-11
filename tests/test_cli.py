from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_quant_lab.cli import app
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar

runner = CliRunner()


def write_test_csv(path: Path) -> None:
    """Write a controlled historical CSV file for CLI tests."""

    content = (
        "timestamp,open,high,low,close,tick_volume,spread_points\n"
        "2026-08-01T00:00:00+00:00,"
        "1.1500,1.1520,1.1490,1.1510,1000,10\n"
        "2026-08-01T00:15:00+00:00,"
        "1.1510,1.1530,1.1500,1.1520,1100,11\n"
    )

    path.write_text(
        content,
        encoding="utf-8",
    )


def make_market_bar(
    minute: int,
) -> MarketBar:
    """Create one controlled canonical market bar."""

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
        real_volume=250,
        spread_points=10,
    )


class FakeMetaTrader5MarketDataSource:
    """Controlled MT5 source used by CLI tests."""

    name = "metatrader5"

    def __init__(
        self,
        **kwargs: object,
    ) -> None:
        self.options = kwargs

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        bars = [
            make_market_bar(0),
            make_market_bar(15),
        ]

        return [
            bar
            for bar in bars
            if start <= bar.timestamp < end
        ]


def test_ingest_csv_command(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "eurusd.csv"
    output_root = tmp_path / "processed"

    write_test_csv(csv_path)

    result = runner.invoke(
        app,
        [
            "ingest-csv",
            str(csv_path),
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Ingestion complete" in result.output
    assert "Source: csv-cli" in result.output
    assert "Bars written: 2" in result.output

    dataset_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "bars.parquet"
    )

    manifest_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "manifest.json"
    )

    assert dataset_path.exists()
    assert manifest_path.exists()


def test_ingest_mt5_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "processed"

    monkeypatch.setattr(
        "ai_quant_lab.cli.MetaTrader5MarketDataSource",
        FakeMetaTrader5MarketDataSource,
    )

    result = runner.invoke(
        app,
        [
            "ingest-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Ingestion complete" in result.output
    assert "Source: metatrader5" in result.output
    assert "Pair: EURUSD" in result.output
    assert "Timeframe: M15" in result.output
    assert "Bars written: 2" in result.output

    dataset_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "bars.parquet"
    )

    manifest_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "manifest.json"
    )

    assert dataset_path.exists()
    assert manifest_path.exists()


def test_update_mt5_command_creates_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "processed"

    monkeypatch.setattr(
        "ai_quant_lab.cli.MetaTrader5MarketDataSource",
        FakeMetaTrader5MarketDataSource,
    )

    result = runner.invoke(
        app,
        [
            "update-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Dataset update complete" in result.output
    assert "Source: metatrader5" in result.output
    assert "Existing bars: 0" in result.output
    assert "Fetched bars: 2" in result.output
    assert "Overlapping bars: 0" in result.output
    assert "New bars: 2" in result.output
    assert "Total bars: 2" in result.output

    dataset_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "bars.parquet"
    )

    manifest_path = (
        output_root
        / "EURUSD"
        / "M15"
        / "manifest.json"
    )

    assert dataset_path.exists()
    assert manifest_path.exists()


def test_backfill_mt5_command_creates_chunked_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "processed"
    monkeypatch.setattr(
        "ai_quant_lab.cli.MetaTrader5MarketDataSource",
        FakeMetaTrader5MarketDataSource,
    )

    result = runner.invoke(
        app,
        [
            "backfill-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-02T00:00:00+00:00",
            "--chunk-days",
            "1",
            "--output-root",
            str(output_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Historical backfill complete" in result.output
    assert "Chunks: 1" in result.output
    assert "New bars: 2" in result.output


def test_update_mt5_command_merges_existing_dataset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "processed"

    monkeypatch.setattr(
        "ai_quant_lab.cli.MetaTrader5MarketDataSource",
        FakeMetaTrader5MarketDataSource,
    )

    first_result = runner.invoke(
        app,
        [
            "ingest-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--output-root",
            str(output_root),
        ],
    )

    assert first_result.exit_code == 0, first_result.output

    update_result = runner.invoke(
        app,
        [
            "update-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--output-root",
            str(output_root),
        ],
    )

    assert update_result.exit_code == 0, update_result.output
    assert "Dataset update complete" in update_result.output
    assert "Existing bars: 2" in update_result.output
    assert "Fetched bars: 2" in update_result.output
    assert "Overlapping bars: 2" in update_result.output
    assert "New bars: 0" in update_result.output
    assert "Total bars: 2" in update_result.output


def test_command_rejects_unsupported_pair(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "market.csv"

    write_test_csv(csv_path)

    result = runner.invoke(
        app,
        [
            "ingest-csv",
            str(csv_path),
            "--pair",
            "EURXXX",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported pair" in result.output


def test_command_rejects_naive_datetime(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "market.csv"

    write_test_csv(csv_path)

    result = runner.invoke(
        app,
        [
            "ingest-csv",
            str(csv_path),
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
        ],
    )

    assert result.exit_code != 0
    assert "timezone information" in result.output


def test_mt5_command_rejects_empty_broker_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ai_quant_lab.cli.MetaTrader5MarketDataSource",
        FakeMetaTrader5MarketDataSource,
    )

    result = runner.invoke(
        app,
        [
            "update-mt5",
            "--pair",
            "EURUSD",
            "--timeframe",
            "M15",
            "--start",
            "2026-08-01T00:00:00+00:00",
            "--end",
            "2026-08-01T01:00:00+00:00",
            "--broker-symbol",
            "   ",
        ],
    )

    assert result.exit_code != 0
    assert "broker symbol cannot be empty" in result.output
