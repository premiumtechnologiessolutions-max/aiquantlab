from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import (
    build_dataset_manifest,
    write_dataset_manifest,
)
from ai_quant_lab.data.ingestion import MarketDataSource
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.data.update import update_market_data

BackfillChunkStatus = Literal[
    "updated",
    "empty",
]


class BackfillChunkResult(BaseModel):
    """Immutable result for one historical backfill interval."""

    model_config = ConfigDict(frozen=True)

    start: datetime
    end: datetime
    status: BackfillChunkStatus

    fetched_bars: int = Field(ge=0)
    overlapping_bars: int = Field(ge=0)
    new_bars: int = Field(ge=0)
    total_bars_after_update: int = Field(ge=0)


class HistoricalBackfillResult(BaseModel):
    """Final result of a multi-chunk historical data backfill."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    pair: ForexPair
    timeframe: Timeframe

    requested_start: datetime
    requested_end: datetime
    chunk_days: int = Field(gt=0)

    chunks_total: int = Field(gt=0)
    chunks_updated: int = Field(ge=0)
    chunks_empty: int = Field(ge=0)

    initial_bars: int = Field(ge=0)
    fetched_bars: int = Field(ge=0)
    new_bars: int = Field(ge=0)
    final_bars: int = Field(gt=0)

    dataset_path: Path
    manifest_path: Path
    dataset_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )

    chunks: tuple[BackfillChunkResult, ...]


class _FixedBatchSource:
    """Expose one already-fetched batch through the data-source contract."""

    def __init__(
        self,
        *,
        source_name: str,
        bars: Sequence[MarketBar],
    ) -> None:
        self._name = source_name
        self._bars = tuple(bars)

    @property
    def name(self) -> str:
        """Return the original market-data source name."""

        return self._name

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        """Return the fixed batch supplied during construction."""

        return self._bars


def build_backfill_intervals(
    *,
    start: datetime,
    end: datetime,
    chunk_days: int = 30,
) -> list[tuple[datetime, datetime]]:
    """Split one UTC interval into contiguous half-open chunks."""

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

    if chunk_days <= 0:
        raise ValueError(
            "Chunk days must be greater than zero.",
        )

    chunk_size = timedelta(
        days=chunk_days,
    )

    intervals: list[
        tuple[
            datetime,
            datetime,
        ]
    ] = []

    current_start = start_utc

    while current_start < end_utc:
        current_end = min(
            current_start + chunk_size,
            end_utc,
        )

        intervals.append(
            (
                current_start,
                current_end,
            )
        )

        current_start = current_end

    return intervals


def backfill_market_data(
    *,
    source: MarketDataSource,
    store: ParquetMarketStore,
    pair: ForexPair,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    chunk_days: int = 30,
) -> HistoricalBackfillResult:
    """Backfill historical data safely across multiple time chunks."""

    intervals = build_backfill_intervals(
        start=start,
        end=end,
        chunk_days=chunk_days,
    )

    requested_start = intervals[0][0]
    requested_end = intervals[-1][1]

    dataset_path = store.dataset_path(
        pair,
        timeframe,
    )

    if dataset_path.exists():
        initial_bars = len(
            store.read_bars(
                pair,
                timeframe,
            )
        )
    else:
        initial_bars = 0

    chunk_results: list[BackfillChunkResult] = []

    for chunk_start, chunk_end in intervals:
        incoming_bars = list(
            source.fetch_bars(
                pair=pair,
                timeframe=timeframe,
                start=chunk_start,
                end=chunk_end,
            )
        )

        if not incoming_bars:
            current_total = (
                len(
                    store.read_bars(
                        pair,
                        timeframe,
                    )
                )
                if dataset_path.exists()
                else 0
            )

            chunk_results.append(
                BackfillChunkResult(
                    start=chunk_start,
                    end=chunk_end,
                    status="empty",
                    fetched_bars=0,
                    overlapping_bars=0,
                    new_bars=0,
                    total_bars_after_update=current_total,
                )
            )

            continue

        batch_source = _FixedBatchSource(
            source_name=source.name,
            bars=incoming_bars,
        )

        update_result = update_market_data(
            source=batch_source,
            store=store,
            pair=pair,
            timeframe=timeframe,
            start=chunk_start,
            end=chunk_end,
        )

        chunk_results.append(
            BackfillChunkResult(
                start=chunk_start,
                end=chunk_end,
                status="updated",
                fetched_bars=update_result.fetched_bars,
                overlapping_bars=update_result.overlapping_bars,
                new_bars=update_result.new_bars,
                total_bars_after_update=update_result.total_bars,
            )
        )

    if not dataset_path.exists():
        raise ValueError(
            "Historical backfill completed without any market bars.",
        )

    final_bars = store.read_bars(
        pair,
        timeframe,
    )

    manifest = build_dataset_manifest(
        store,
        pair,
        timeframe,
    )

    manifest_path = write_dataset_manifest(
        manifest,
        root=store.root,
    )

    fetched_bars = sum(
        chunk.fetched_bars
        for chunk in chunk_results
    )

    chunks_updated = sum(
        chunk.status == "updated"
        for chunk in chunk_results
    )

    chunks_empty = sum(
        chunk.status == "empty"
        for chunk in chunk_results
    )

    return HistoricalBackfillResult(
        source=source.name,
        pair=pair,
        timeframe=timeframe,
        requested_start=requested_start,
        requested_end=requested_end,
        chunk_days=chunk_days,
        chunks_total=len(chunk_results),
        chunks_updated=chunks_updated,
        chunks_empty=chunks_empty,
        initial_bars=initial_bars,
        fetched_bars=fetched_bars,
        new_bars=max(
            len(final_bars) - initial_bars,
            0,
        ),
        final_bars=len(final_bars),
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        dataset_sha256=manifest.sha256,
        chunks=tuple(chunk_results),
    )


def _normalize_boundary(
    value: datetime,
    *,
    name: str,
) -> datetime:
    """Require timezone information and normalize a boundary to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"The {name} time must include timezone information.",
        )

    return value.astimezone(UTC)