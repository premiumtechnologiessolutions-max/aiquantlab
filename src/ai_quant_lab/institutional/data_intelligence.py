from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from itertools import pairwise
from math import log
from statistics import median
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.trading_calendar import ForexTradingCalendar


class DataCapability(StrEnum):
    """Market inputs that may or may not be supplied by the active provider."""

    OHLC = "ohlc"
    TICK_VOLUME = "tick_volume"
    REAL_VOLUME = "real_volume"
    BID_ASK_SPREAD = "bid_ask_spread"
    ORDER_BOOK = "order_book"
    TRADE_FLOW = "trade_flow"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATIONS = "liquidations"
    OPTIONS_VOLATILITY = "options_volatility"
    MACRO = "macro"
    CROSS_ASSET = "cross_asset"
    NEWS_SENTIMENT = "news_sentiment"


class DatasetQualityReport(BaseModel):
    """Content-addressed data version and observable quality evidence."""

    model_config = ConfigDict(frozen=True)

    dataset_version_id: str
    source: str
    pair: ForexPair
    timeframe: Timeframe
    first_timestamp: datetime
    last_timestamp: datetime
    bar_count: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_intervals: int = Field(ge=0)
    missing_intervals: int = Field(ge=0)
    missing_ratio: float = Field(ge=0, le=1)
    duplicate_timestamps: int = Field(ge=0)
    non_monotonic_rows: int = Field(ge=0)
    return_outliers: int = Field(ge=0)
    zero_volume_rows: int = Field(ge=0)
    median_spread_points: float = Field(ge=0)
    maximum_spread_points: float = Field(ge=0)
    quality_score: float = Field(ge=0, le=1)
    available_capabilities: tuple[DataCapability, ...]
    unavailable_capabilities: tuple[DataCapability, ...]
    warnings: tuple[str, ...]
    inspected_at: datetime


class DataIntelligenceEngine:
    """Collect observable dataset evidence without inventing unavailable feeds."""

    _SECONDS_BY_TIMEFRAME: ClassVar[dict[str, int]] = {
        "M1": 60,
        "M5": 5 * 60,
        "M15": 15 * 60,
        "H1": 60 * 60,
        "H4": 4 * 60 * 60,
        "D1": 24 * 60 * 60,
    }

    def inspect(
        self,
        bars: Sequence[MarketBar],
        *,
        source: str = "mt5_demo",
        extra_capabilities: Sequence[DataCapability] = (),
    ) -> DatasetQualityReport:
        """Validate, fingerprint, and score one exact causal bar snapshot."""

        if not bars:
            raise ValueError("Data intelligence requires at least one market bar.")

        pair = bars[0].pair
        timeframe = bars[0].timeframe

        if any(bar.pair != pair or bar.timeframe != timeframe for bar in bars):
            raise ValueError("A dataset version must contain one pair and timeframe.")

        timestamps = [bar.timestamp.astimezone(UTC) for bar in bars]
        duplicate_timestamps = len(timestamps) - len(set(timestamps))
        non_monotonic = sum(current <= previous for previous, current in pairwise(timestamps))
        ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
        interval_seconds = self._SECONDS_BY_TIMEFRAME.get(str(timeframe))
        missing_intervals = 0
        expected_intervals = max(0, len(ordered) - 1)

        if interval_seconds is not None:
            calendar = ForexTradingCalendar()
            gaps = [
                calendar.count_missing_bar_openings(
                    previous=previous.timestamp,
                    current=current.timestamp,
                    interval_seconds=interval_seconds,
                )
                for previous, current in pairwise(ordered)
            ]
            missing_intervals = sum(gaps)
            expected_intervals += missing_intervals

        returns = [
            log(current.close / previous.close)
            for previous, current in pairwise(ordered)
            if previous.close > 0 and current.close > 0
        ]
        return_outliers = _mad_outlier_count(returns)
        zero_volume_rows = sum(bar.tick_volume == 0 for bar in ordered)
        spreads = [bar.spread_points for bar in ordered]
        median_spread = median(spreads) if spreads else 0.0
        maximum_spread = max(spreads, default=0.0)
        missing_ratio = missing_intervals / expected_intervals if expected_intervals > 0 else 0.0
        outlier_ratio = return_outliers / max(1, len(returns))
        zero_volume_ratio = zero_volume_rows / len(ordered)
        quality_score = max(
            0.0,
            min(
                1.0,
                1.0
                - min(0.45, missing_ratio * 2.0)
                - min(0.20, duplicate_timestamps / len(ordered))
                - min(0.15, non_monotonic / len(ordered))
                - min(0.10, outlier_ratio)
                - min(0.10, zero_volume_ratio),
            ),
        )
        available = {
            DataCapability.OHLC,
            DataCapability.TICK_VOLUME,
            DataCapability.BID_ASK_SPREAD,
            *extra_capabilities,
        }

        if any(bar.real_volume not in {None, 0.0} for bar in ordered):
            available.add(DataCapability.REAL_VOLUME)

        unavailable = tuple(
            capability for capability in DataCapability if capability not in available
        )
        warnings: list[str] = []

        if missing_ratio > 0.01:
            warnings.append(f"Missing interval ratio is {missing_ratio:.2%}.")

        if duplicate_timestamps:
            warnings.append(f"Found {duplicate_timestamps} duplicate timestamps.")

        if non_monotonic:
            warnings.append(f"Found {non_monotonic} non-monotonic rows.")

        if maximum_spread > max(50.0, median_spread * 3.0):
            warnings.append("Observed a material spread spike in this dataset version.")

        digest = _dataset_digest(ordered)

        return DatasetQualityReport(
            dataset_version_id=f"dataset_{digest[:20]}",
            source=source,
            pair=pair,
            timeframe=timeframe,
            first_timestamp=ordered[0].timestamp,
            last_timestamp=ordered[-1].timestamp,
            bar_count=len(ordered),
            sha256=digest,
            expected_intervals=expected_intervals,
            missing_intervals=missing_intervals,
            missing_ratio=missing_ratio,
            duplicate_timestamps=duplicate_timestamps,
            non_monotonic_rows=non_monotonic,
            return_outliers=return_outliers,
            zero_volume_rows=zero_volume_rows,
            median_spread_points=median_spread,
            maximum_spread_points=maximum_spread,
            quality_score=quality_score,
            available_capabilities=tuple(sorted(available, key=lambda item: item.value)),
            unavailable_capabilities=unavailable,
            warnings=tuple(warnings),
            inspected_at=datetime.now(UTC),
        )


def _dataset_digest(bars: Sequence[MarketBar]) -> str:
    digest = sha256()

    for bar in bars:
        digest.update(
            (
                f"{bar.pair}|{bar.timeframe}|{bar.timestamp.isoformat()}|"
                f"{bar.open:.12g}|{bar.high:.12g}|{bar.low:.12g}|{bar.close:.12g}|"
                f"{bar.tick_volume}|{bar.real_volume}|{bar.spread_points:.12g}\n"
            ).encode()
        )

    return digest.hexdigest()


def _mad_outlier_count(values: Sequence[float]) -> int:
    if len(values) < 5:
        return 0

    center = median(values)
    deviations = [abs(value - center) for value in values]
    mad = median(deviations)

    if mad <= 0:
        return sum(value != center for value in values)

    robust_scale = 1.4826 * mad

    return sum(abs(value - center) / robust_scale > 8.0 for value in values)
