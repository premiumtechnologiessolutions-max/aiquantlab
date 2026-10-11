from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar

RateValue = int | float


class MetaTrader5RateRow(Protocol):
    """One structured rate row returned by MetaTrader 5."""

    def __getitem__(
        self,
        key: str,
    ) -> RateValue:
        """Return one named numeric field from the rate row."""

        ...


class MetaTrader5Api(Protocol):
    """Small read-only subset of the MetaTrader 5 Python API."""

    TIMEFRAME_M1: int
    TIMEFRAME_M5: int
    TIMEFRAME_M15: int
    TIMEFRAME_H1: int
    TIMEFRAME_H4: int
    TIMEFRAME_D1: int

    def initialize(
        self,
        *args: object,
        **kwargs: object,
    ) -> bool:
        """Connect to a MetaTrader 5 terminal."""

        ...

    def shutdown(self) -> None:
        """Close the terminal connection."""

        ...

    def last_error(self) -> tuple[int, str]:
        """Return the most recent MetaTrader 5 error."""

        ...

    def symbol_select(
        self,
        symbol: str,
        enable: bool,
    ) -> bool:
        """Enable or disable a symbol in Market Watch."""

        ...

    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> object:
        """Return historical rates for a requested interval."""

        ...


class UnavailableMetaTrader5Api:
    """Portable placeholder used when the Windows-only package is absent."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def initialize(
        self,
        *args: object,
        **kwargs: object,
    ) -> bool:
        """Report that no local terminal integration is available."""

        return False

    def shutdown(self) -> None:
        """Perform no work because no connection was opened."""

    def last_error(self) -> tuple[int, str]:
        """Return a readable platform/package error."""

        return (
            1,
            "MetaTrader5 Python package or Windows terminal is unavailable",
        )

    def symbol_select(
        self,
        symbol: str,
        enable: bool,
    ) -> bool:
        """Reject symbol selection without a terminal."""

        return False

    def copy_rates_range(
        self,
        symbol: str,
        timeframe: int,
        start: datetime,
        end: datetime,
    ) -> None:
        """Return no rates without a terminal."""


try:
    import MetaTrader5 as _mt5  # type: ignore[import-not-found]

    DEFAULT_MT5_API = cast(MetaTrader5Api, _mt5)
except ModuleNotFoundError:
    DEFAULT_MT5_API = UnavailableMetaTrader5Api()


class MetaTrader5MarketDataSource:
    """Read historical market bars from a MetaTrader 5 terminal."""

    def __init__(
        self,
        *,
        terminal_path: str | Path | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        timeout_ms: int = 60_000,
        portable: bool = False,
        symbol_map: Mapping[ForexPair, str] | None = None,
        api: MetaTrader5Api | None = None,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError(
                "MetaTrader 5 timeout must be greater than zero.",
            )

        self._terminal_path = (
            Path(terminal_path)
            if terminal_path is not None
            else None
        )

        self._login = login
        self._password = password
        self._server = server
        self._timeout_ms = timeout_ms
        self._portable = portable
        self._symbol_map = dict(symbol_map or {})

        if api is None:
            self._api = DEFAULT_MT5_API
        else:
            self._api = api

    @property
    def name(self) -> str:
        """Return the market-data source name."""

        return "metatrader5"

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        """Fetch canonical bars from MetaTrader 5."""

        start_utc = _normalize_boundary(
            start,
            name="start",
        )

        end_utc = _normalize_boundary(
            end,
            name="end",
        )

        if start_utc >= end_utc:
            raise ValueError(
                "Start time must be earlier than end time.",
            )

        symbol = self._symbol_map.get(
            pair,
            pair,
        )

        mt5_timeframe = self._resolve_timeframe(timeframe)

        self._initialize_terminal()

        try:
            if not self._api.symbol_select(symbol, True):
                raise RuntimeError(
                    "MetaTrader 5 could not select symbol "
                    f"'{symbol}': {self._last_error_text()}",
                )

            rates_object = self._api.copy_rates_range(
                symbol,
                mt5_timeframe,
                start_utc,
                end_utc,
            )

            if rates_object is None:
                raise RuntimeError(
                    "MetaTrader 5 could not return rates for "
                    f"'{symbol}': {self._last_error_text()}",
                )

            rates = cast(
                Sequence[MetaTrader5RateRow],
                rates_object,
            )

            bars = [
                self._convert_rate(
                    rate=rate,
                    pair=pair,
                    timeframe=timeframe,
                )
                for rate in rates
            ]

            filtered_bars = [
                bar
                for bar in bars
                if start_utc <= bar.timestamp < end_utc
            ]

            return sorted(
                filtered_bars,
                key=lambda bar: bar.timestamp,
            )
        finally:
            self._api.shutdown()

    def _initialize_terminal(self) -> None:
        """Open a connection to the configured terminal."""

        options: dict[str, object] = {
            "timeout": self._timeout_ms,
            "portable": self._portable,
        }

        if self._login is not None:
            options["login"] = self._login

        if self._password is not None:
            options["password"] = self._password

        if self._server is not None:
            options["server"] = self._server

        if self._terminal_path is None:
            connected = self._api.initialize(
                **options,
            )
        else:
            connected = self._api.initialize(
                str(self._terminal_path),
                **options,
            )

        if not connected:
            raise RuntimeError(
                "MetaTrader 5 initialization failed: "
                f"{self._last_error_text()}",
            )

    def _resolve_timeframe(
        self,
        timeframe: Timeframe,
    ) -> int:
        """Convert the project timeframe to an MT5 constant."""

        timeframe_map: dict[Timeframe, int] = {
            "M1": self._api.TIMEFRAME_M1,
            "M5": self._api.TIMEFRAME_M5,
            "M15": self._api.TIMEFRAME_M15,
            "H1": self._api.TIMEFRAME_H1,
            "H4": self._api.TIMEFRAME_H4,
            "D1": self._api.TIMEFRAME_D1,
        }

        return timeframe_map[timeframe]

    def _convert_rate(
        self,
        *,
        rate: MetaTrader5RateRow,
        pair: ForexPair,
        timeframe: Timeframe,
    ) -> MarketBar:
        """Convert one MetaTrader 5 rate to a canonical bar."""

        timestamp_seconds = int(
            _read_rate_field(
                rate,
                "time",
            )
        )

        return MarketBar(
            pair=pair,
            timeframe=timeframe,
            timestamp=datetime.fromtimestamp(
                timestamp_seconds,
                tz=UTC,
            ),
            open=float(
                _read_rate_field(
                    rate,
                    "open",
                )
            ),
            high=float(
                _read_rate_field(
                    rate,
                    "high",
                )
            ),
            low=float(
                _read_rate_field(
                    rate,
                    "low",
                )
            ),
            close=float(
                _read_rate_field(
                    rate,
                    "close",
                )
            ),
            tick_volume=int(
                _read_rate_field(
                    rate,
                    "tick_volume",
                )
            ),
            real_volume=float(
                _read_rate_field(
                    rate,
                    "real_volume",
                )
            ),
            spread_points=float(
                _read_rate_field(
                    rate,
                    "spread",
                )
            ),
        )

    def _last_error_text(self) -> str:
        """Return the current MT5 error as readable text."""

        code, message = self._api.last_error()

        return f"{code}: {message}"


def _normalize_boundary(
    value: datetime,
    *,
    name: str,
) -> datetime:
    """Require a timezone-aware boundary and convert it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"The {name} time must include timezone information.",
        )

    return value.astimezone(UTC)


def _read_rate_field(
    rate: MetaTrader5RateRow,
    field: str,
) -> RateValue:
    """Read a required numeric field from one structured MT5 rate."""

    try:
        return rate[field]
    except (IndexError, KeyError, ValueError) as error:
        raise ValueError(
            f"MetaTrader 5 rate is missing field '{field}'.",
        ) from error
