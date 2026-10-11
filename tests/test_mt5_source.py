from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.config import Timeframe
from ai_quant_lab.data.mt5_source import MetaTrader5MarketDataSource


class FakeMetaTrader5Api:
    """Controlled read-only MetaTrader 5 API for automated tests."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def __init__(
        self,
        *,
        rates: object = (),
        initialize_result: bool = True,
        symbol_select_result: bool = True,
    ) -> None:
        self.rates = rates
        self.initialize_result = initialize_result
        self.symbol_select_result = symbol_select_result

        self.initialize_calls: list[
            tuple[
                tuple[object, ...],
                dict[str, object],
            ]
        ] = []

        self.symbol_select_calls: list[
            tuple[str, bool]
        ] = []

        self.copy_rates_calls: list[
            tuple[
                str,
                int,
                datetime,
                datetime,
            ]
        ] = []

        self.shutdown_count = 0

    def initialize(
        self,
        *args: object,
        **kwargs: object,
    ) -> bool:
        self.initialize_calls.append(
            (
                args,
                kwargs,
            )
        )

        return self.initialize_result

    def shutdown(self) -> None:
        self.shutdown_count += 1

    def last_error(self) -> tuple[int, str]:
        return (
            500,
            "controlled test error",
        )

    def symbol_select(
        self,
        symbol: str,
        enable: bool,
    ) -> bool:
        self.symbol_select_calls.append(
            (
                symbol,
                enable,
            )
        )

        return self.symbol_select_result

    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> object:
        self.copy_rates_calls.append(
            (
                symbol,
                timeframe,
                start,
                end,
            )
        )

        return self.rates


def make_rate(
    minute: int,
    *,
    open_price: float = 1.1500,
    close_price: float = 1.1510,
) -> dict[str, object]:
    timestamp = datetime(
        2026,
        8,
        1,
        tzinfo=UTC,
    ) + timedelta(minutes=minute)

    return {
        "time": int(timestamp.timestamp()),
        "open": open_price,
        "high": max(
            open_price,
            close_price,
        )
        + 0.0010,
        "low": min(
            open_price,
            close_price,
        )
        - 0.0010,
        "close": close_price,
        "tick_volume": 1000 + minute,
        "spread": 10,
        "real_volume": 250,
    }


def test_mt5_source_reads_sorts_and_converts_bars() -> None:
    api = FakeMetaTrader5Api(
        rates=[
            make_rate(30),
            make_rate(0),
            make_rate(15),
        ]
    )

    source = MetaTrader5MarketDataSource(
        api=api,
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

    assert source.name == "metatrader5"
    assert len(bars) == 3

    assert [
        bar.timestamp.minute
        for bar in bars
    ] == [
        0,
        15,
        30,
    ]

    assert bars[0].pair == "EURUSD"
    assert bars[0].timeframe == "M15"
    assert bars[0].timestamp.tzinfo == UTC
    assert bars[0].tick_volume == 1000
    assert bars[0].real_volume == 250.0
    assert bars[0].spread_points == 10.0

    assert api.initialize_calls == [
        (
            (),
            {
                "timeout": 60_000,
                "portable": False,
            },
        )
    ]

    assert api.symbol_select_calls == [
        (
            "EURUSD",
            True,
        )
    ]

    assert api.copy_rates_calls[0][0] == "EURUSD"
    assert api.copy_rates_calls[0][1] == api.TIMEFRAME_M15
    assert api.shutdown_count == 1


def test_mt5_source_uses_symbol_mapping() -> None:
    api = FakeMetaTrader5Api(
        rates=[
            make_rate(0),
        ]
    )

    source = MetaTrader5MarketDataSource(
        api=api,
        symbol_map={
            "EURUSD": "EURUSD.a",
        },
    )

    source.fetch_bars(
        pair="EURUSD",
        timeframe="M5",
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
            0,
            10,
            tzinfo=UTC,
        ),
    )

    assert api.symbol_select_calls == [
        (
            "EURUSD.a",
            True,
        )
    ]

    assert api.copy_rates_calls[0][0] == "EURUSD.a"
    assert api.copy_rates_calls[0][1] == api.TIMEFRAME_M5


def test_mt5_source_passes_terminal_configuration() -> None:
    api = FakeMetaTrader5Api(
        rates=[
            make_rate(0),
        ]
    )

    terminal_path = Path(
        "C:/Program Files/MetaTrader 5/terminal64.exe"
    )

    source = MetaTrader5MarketDataSource(
        terminal_path=terminal_path,
        login=12345678,
        password="test-password",
        server="Test-Demo",
        timeout_ms=30_000,
        portable=True,
        api=api,
    )

    source.fetch_bars(
        pair="GBPUSD",
        timeframe="H1",
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

    assert api.initialize_calls == [
        (
            (
                str(terminal_path),
            ),
            {
                "timeout": 30_000,
                "portable": True,
                "login": 12345678,
                "password": "test-password",
                "server": "Test-Demo",
            },
        )
    ]

    assert api.copy_rates_calls[0][1] == api.TIMEFRAME_H1
    assert api.shutdown_count == 1


def test_mt5_source_filters_end_boundary() -> None:
    api = FakeMetaTrader5Api(
        rates=[
            make_rate(0),
            make_rate(15),
            make_rate(30),
        ]
    )

    source = MetaTrader5MarketDataSource(
        api=api,
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
            0,
            30,
            tzinfo=UTC,
        ),
    )

    assert len(bars) == 2

    assert [
        bar.timestamp.minute
        for bar in bars
    ] == [
        0,
        15,
    ]


def test_mt5_source_rejects_naive_boundary() -> None:
    api = FakeMetaTrader5Api()

    source = MetaTrader5MarketDataSource(
        api=api,
    )

    with pytest.raises(
        ValueError,
        match="timezone information",
    ):
        source.fetch_bars(
            pair="EURUSD",
            timeframe="M15",
            # Intentionally naive to verify validation.
            start=datetime(2026, 8, 1),  # noqa: DTZ001
            end=datetime(
                2026,
                8,
                1,
                1,
                tzinfo=UTC,
            ),
        )

    assert api.initialize_calls == []


def test_mt5_source_rejects_invalid_interval() -> None:
    api = FakeMetaTrader5Api()

    source = MetaTrader5MarketDataSource(
        api=api,
    )

    boundary = datetime(
        2026,
        8,
        1,
        tzinfo=UTC,
    )

    with pytest.raises(
        ValueError,
        match="earlier than end",
    ):
        source.fetch_bars(
            pair="EURUSD",
            timeframe="M15",
            start=boundary,
            end=boundary,
        )

    assert api.initialize_calls == []


def test_mt5_source_reports_initialization_failure() -> None:
    api = FakeMetaTrader5Api(
        initialize_result=False,
    )

    source = MetaTrader5MarketDataSource(
        api=api,
    )

    with pytest.raises(
        RuntimeError,
        match="initialization failed",
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

    assert api.shutdown_count == 0


def test_mt5_source_reports_symbol_selection_failure() -> None:
    api = FakeMetaTrader5Api(
        symbol_select_result=False,
    )

    source = MetaTrader5MarketDataSource(
        api=api,
    )

    with pytest.raises(
        RuntimeError,
        match="could not select symbol",
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

    assert api.shutdown_count == 1


def test_mt5_source_reports_missing_rates() -> None:
    api = FakeMetaTrader5Api(
        rates=None,
    )

    source = MetaTrader5MarketDataSource(
        api=api,
    )

    with pytest.raises(
        RuntimeError,
        match="could not return rates",
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

    assert api.shutdown_count == 1


@pytest.mark.parametrize(
    ("timeframe", "expected_constant"),
    (("M1", 1), ("H4", 240), ("D1", 1440)),
)
def test_mt5_source_supports_extended_research_timeframes(
    timeframe: Timeframe,
    expected_constant: int,
) -> None:
    api = FakeMetaTrader5Api(rates=[make_rate(0)])
    source = MetaTrader5MarketDataSource(api=api)

    source.fetch_bars(
        pair="EURUSD",
        timeframe=timeframe,
        start=datetime(2026, 8, 1, tzinfo=UTC),
        end=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert api.copy_rates_calls[0][1] == expected_constant
