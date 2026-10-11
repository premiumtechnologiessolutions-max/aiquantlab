from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

SECONDS_PER_WEEK: Final[int] = 7 * 24 * 60 * 60


class ForexTradingCalendar:
    """Represent the standard weekly foreign-exchange trading schedule."""

    def __init__(
        self,
        *,
        weekly_open_weekday: int = 6,
        weekly_open_hour_utc: int = 22,
        weekly_close_weekday: int = 4,
        weekly_close_hour_utc: int = 22,
    ) -> None:
        self._validate_weekday(
            weekly_open_weekday,
            name="weekly_open_weekday",
        )

        self._validate_weekday(
            weekly_close_weekday,
            name="weekly_close_weekday",
        )

        self._validate_hour(
            weekly_open_hour_utc,
            name="weekly_open_hour_utc",
        )

        self._validate_hour(
            weekly_close_hour_utc,
            name="weekly_close_hour_utc",
        )

        self.weekly_open_weekday = weekly_open_weekday
        self.weekly_open_hour_utc = weekly_open_hour_utc
        self.weekly_close_weekday = weekly_close_weekday
        self.weekly_close_hour_utc = weekly_close_hour_utc

        self._weekly_open_second = self._second_of_week(
            weekday=weekly_open_weekday,
            hour=weekly_open_hour_utc,
        )

        self._weekly_close_second = self._second_of_week(
            weekday=weekly_close_weekday,
            hour=weekly_close_hour_utc,
        )

        if self._weekly_open_second == self._weekly_close_second:
            raise ValueError(
                "Weekly market open and close cannot be identical.",
            )

    def is_market_open(
        self,
        timestamp: datetime,
    ) -> bool:
        """Return whether the FX market is scheduled to be open."""

        timestamp_utc = self._normalize_timestamp(timestamp)
        second_of_week = self._timestamp_second_of_week(
            timestamp_utc,
        )

        if self._weekly_open_second < self._weekly_close_second:
            return (
                self._weekly_open_second
                <= second_of_week
                < self._weekly_close_second
            )

        return (
            second_of_week >= self._weekly_open_second
            or second_of_week < self._weekly_close_second
        )

    def count_expected_bars(
        self,
        *,
        start: datetime,
        end: datetime,
        interval_seconds: int,
    ) -> int:
        """Count expected bar openings inside a half-open time interval."""

        if interval_seconds <= 0:
            raise ValueError(
                "The bar interval must be greater than zero.",
            )

        start_utc = self._normalize_timestamp(start)
        end_utc = self._normalize_timestamp(end)

        if start_utc >= end_utc:
            raise ValueError(
                "Start time must be earlier than end time.",
            )

        expected_bars = 0
        current = start_utc

        while current < end_utc:
            if self.is_market_open(current):
                expected_bars += 1

            current += timedelta(seconds=interval_seconds)

        return expected_bars

    def count_missing_bar_openings(
        self,
        *,
        previous: datetime,
        current: datetime,
        interval_seconds: int,
    ) -> int:
        """Count scheduled bar openings missing between two observed bars."""

        if interval_seconds <= 0:
            raise ValueError(
                "The bar interval must be greater than zero.",
            )

        previous_utc = self._normalize_timestamp(previous)
        current_utc = self._normalize_timestamp(current)

        if previous_utc >= current_utc:
            return 0

        first_possible_missing = previous_utc + timedelta(
            seconds=interval_seconds,
        )

        if first_possible_missing >= current_utc:
            return 0

        return self.count_expected_bars(
            start=first_possible_missing,
            end=current_utc,
            interval_seconds=interval_seconds,
        )

    @staticmethod
    def _normalize_timestamp(
        value: datetime,
    ) -> datetime:
        """Require timezone information and normalize a timestamp to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Trading-calendar timestamps must include timezone information.",
            )

        return value.astimezone(UTC)

    @staticmethod
    def _second_of_week(
        *,
        weekday: int,
        hour: int,
    ) -> int:
        """Convert a weekday and hour to seconds from Monday midnight."""

        return (
            weekday * 24 * 60 * 60
            + hour * 60 * 60
        )

    @staticmethod
    def _timestamp_second_of_week(
        timestamp: datetime,
    ) -> int:
        """Return seconds elapsed since Monday midnight UTC."""

        return (
            timestamp.weekday() * 24 * 60 * 60
            + timestamp.hour * 60 * 60
            + timestamp.minute * 60
            + timestamp.second
        )

    @staticmethod
    def _validate_weekday(
        value: int,
        *,
        name: str,
    ) -> None:
        """Validate a Python weekday number."""

        if not 0 <= value <= 6:
            raise ValueError(
                f"{name} must be between 0 and 6.",
            )

    @staticmethod
    def _validate_hour(
        value: int,
        *,
        name: str,
    ) -> None:
        """Validate a UTC hour."""

        if not 0 <= value <= 23:
            raise ValueError(
                f"{name} must be between 0 and 23.",
            )