from datetime import UTC, datetime

import pytest

from ai_quant_lab.data.trading_calendar import ForexTradingCalendar


def utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
) -> datetime:
    """Create one timezone-aware UTC datetime for calendar tests."""

    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=UTC,
    )


def test_market_is_open_during_weekday() -> None:
    calendar = ForexTradingCalendar()

    assert calendar.is_market_open(
        utc_datetime(2026, 7, 28, 12),
    )


def test_market_is_closed_during_saturday() -> None:
    calendar = ForexTradingCalendar()

    assert not calendar.is_market_open(
        utc_datetime(2026, 8, 1, 12),
    )


def test_weekly_close_boundary_is_exclusive() -> None:
    calendar = ForexTradingCalendar()

    assert calendar.is_market_open(
        utc_datetime(2026, 7, 31, 21, 59),
    )

    assert not calendar.is_market_open(
        utc_datetime(2026, 7, 31, 22),
    )


def test_weekly_open_boundary_is_inclusive() -> None:
    calendar = ForexTradingCalendar()

    assert not calendar.is_market_open(
        utc_datetime(2026, 8, 2, 21, 59),
    )

    assert calendar.is_market_open(
        utc_datetime(2026, 8, 2, 22),
    )


def test_count_expected_bars_across_weekend() -> None:
    calendar = ForexTradingCalendar()

    expected_bars = calendar.count_expected_bars(
        start=utc_datetime(2026, 7, 31, 21),
        end=utc_datetime(2026, 8, 3),
        interval_seconds=60 * 60,
    )

    assert expected_bars == 3


def test_count_missing_bar_openings_ignores_market_closure() -> None:
    calendar = ForexTradingCalendar()

    missing_bars = calendar.count_missing_bar_openings(
        previous=utc_datetime(2026, 7, 31, 21),
        current=utc_datetime(2026, 8, 2, 23),
        interval_seconds=60 * 60,
    )

    assert missing_bars == 1


def test_consecutive_bars_have_no_missing_openings() -> None:
    calendar = ForexTradingCalendar()

    missing_bars = calendar.count_missing_bar_openings(
        previous=utc_datetime(2026, 7, 28, 10),
        current=utc_datetime(2026, 7, 28, 10, 15),
        interval_seconds=15 * 60,
    )

    assert missing_bars == 0


def test_calendar_supports_custom_weekly_schedule() -> None:
    calendar = ForexTradingCalendar(
        weekly_open_weekday=0,
        weekly_open_hour_utc=0,
        weekly_close_weekday=4,
        weekly_close_hour_utc=24 - 1,
    )

    assert calendar.is_market_open(
        utc_datetime(2026, 7, 27),
    )

    assert not calendar.is_market_open(
        utc_datetime(2026, 8, 1),
    )


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        (
            "weekly_open_weekday",
            -1,
            "between 0 and 6",
        ),
        (
            "weekly_close_weekday",
            7,
            "between 0 and 6",
        ),
        (
            "weekly_open_hour_utc",
            -1,
            "between 0 and 23",
        ),
        (
            "weekly_close_hour_utc",
            24,
            "between 0 and 23",
        ),
    ],
)
def test_calendar_rejects_invalid_configuration(
    keyword: str,
    value: int,
    message: str,
) -> None:
    options: dict[str, int] = {
        keyword: value,
    }

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ForexTradingCalendar(**options)


def test_calendar_rejects_identical_open_and_close() -> None:
    with pytest.raises(
        ValueError,
        match="cannot be identical",
    ):
        ForexTradingCalendar(
            weekly_open_weekday=0,
            weekly_open_hour_utc=8,
            weekly_close_weekday=0,
            weekly_close_hour_utc=8,
        )


def test_calendar_rejects_naive_timestamp() -> None:
    calendar = ForexTradingCalendar()

    with pytest.raises(
        ValueError,
        match="timezone information",
    ):
        calendar.is_market_open(
            # Intentionally naive to verify validation.
            datetime(2026, 8, 1, 12),  # noqa: DTZ001
        )


def test_calendar_rejects_invalid_bar_interval() -> None:
    calendar = ForexTradingCalendar()

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        calendar.count_expected_bars(
            start=utc_datetime(2026, 7, 28),
            end=utc_datetime(2026, 7, 29),
            interval_seconds=0,
        )


def test_calendar_rejects_invalid_time_range() -> None:
    calendar = ForexTradingCalendar()
    boundary = utc_datetime(2026, 7, 28)

    with pytest.raises(
        ValueError,
        match="earlier than end",
    ):
        calendar.count_expected_bars(
            start=boundary,
            end=boundary,
            interval_seconds=15 * 60,
        )