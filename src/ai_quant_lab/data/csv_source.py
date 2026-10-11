from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar

REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread_points",
    }
)


class CsvMarketDataSource:
    """Read canonical historical market bars from a CSV file."""

    def __init__(
        self,
        path: str | Path,
        *,
        source_name: str = "csv",
    ) -> None:
        self.path = Path(path)
        self._name = source_name

    @property
    def name(self) -> str:
        """Return the configured source name."""

        return self._name

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        """Read bars inside the requested UTC time interval."""

        if not self.path.exists():
            raise FileNotFoundError(
                f"CSV file does not exist: {self.path}",
            )

        bars: list[MarketBar] = []

        with self.path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as stream:
            reader = csv.DictReader(stream)

            fieldnames = set(reader.fieldnames or [])
            missing_columns = REQUIRED_COLUMNS - fieldnames

            if missing_columns:
                missing_text = ", ".join(sorted(missing_columns))

                raise ValueError(
                    f"CSV is missing required columns: {missing_text}",
                )

            for row_number, row in enumerate(
                reader,
                start=2,
            ):
                timestamp = _parse_timestamp(
                    _required_text(
                        row,
                        "timestamp",
                        row_number,
                    ),
                    row_number=row_number,
                )

                if not start <= timestamp < end:
                    continue

                bars.append(
                    MarketBar(
                        pair=pair,
                        timeframe=timeframe,
                        timestamp=timestamp,
                        open=_parse_float(
                            row,
                            "open",
                            row_number,
                        ),
                        high=_parse_float(
                            row,
                            "high",
                            row_number,
                        ),
                        low=_parse_float(
                            row,
                            "low",
                            row_number,
                        ),
                        close=_parse_float(
                            row,
                            "close",
                            row_number,
                        ),
                        tick_volume=_parse_integer(
                            row,
                            "tick_volume",
                            row_number,
                        ),
                        real_volume=_parse_optional_float(
                            row,
                            "real_volume",
                            row_number,
                        ),
                        spread_points=_parse_float(
                            row,
                            "spread_points",
                            row_number,
                        ),
                    )
                )

        return bars


def _required_text(
    row: Mapping[str, object],
    column: str,
    row_number: int,
) -> str:
    """Read one required non-empty CSV value."""

    value = row.get(column)

    if value is None:
        raise ValueError(
            f"Missing value for '{column}' on CSV row {row_number}.",
        )

    text = str(value).strip()

    if not text:
        raise ValueError(
            f"Empty value for '{column}' on CSV row {row_number}.",
        )

    return text


def _parse_timestamp(
    value: str,
    *,
    row_number: int,
) -> datetime:
    """Parse an ISO timestamp and normalize it to UTC."""

    normalized_value = value.replace("Z", "+00:00")

    try:
        timestamp = datetime.fromisoformat(normalized_value)
    except ValueError as error:
        raise ValueError(
            f"Invalid timestamp on CSV row {row_number}: {value}",
        ) from error

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(
            f"Timestamp must include timezone on CSV row {row_number}.",
        )

    return timestamp.astimezone(UTC)


def _parse_float(
    row: Mapping[str, object],
    column: str,
    row_number: int,
) -> float:
    """Parse one required floating-point value."""

    value = _required_text(
        row,
        column,
        row_number,
    )

    try:
        return float(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid number for '{column}' on CSV row {row_number}.",
        ) from error


def _parse_integer(
    row: Mapping[str, object],
    column: str,
    row_number: int,
) -> int:
    """Parse one required integer value."""

    value = _required_text(
        row,
        column,
        row_number,
    )

    try:
        parsed_value = float(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid integer for '{column}' on CSV row {row_number}.",
        ) from error

    if not parsed_value.is_integer():
        raise ValueError(
            f"'{column}' must be an integer on CSV row {row_number}.",
        )

    return int(parsed_value)


def _parse_optional_float(
    row: Mapping[str, object],
    column: str,
    row_number: int,
) -> float | None:
    """Parse an optional floating-point value."""

    value = row.get(column)

    if value is None or not str(value).strip():
        return None

    try:
        return float(str(value).strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid number for '{column}' on CSV row {row_number}.",
        ) from error