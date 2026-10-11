from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import (
    build_dataset_manifest,
    write_dataset_manifest,
)
from ai_quant_lab.data.ingestion import MarketDataSource
from ai_quant_lab.data.merge import merge_market_bars
from ai_quant_lab.data.storage import ParquetMarketStore


class DatasetUpdateResult(BaseModel):
    """Immutable result of one historical dataset update."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    pair: ForexPair
    timeframe: Timeframe

    requested_start: datetime
    requested_end: datetime

    existing_bars: int = Field(ge=0)
    fetched_bars: int = Field(gt=0)
    overlapping_bars: int = Field(ge=0)
    new_bars: int = Field(ge=0)
    total_bars: int = Field(gt=0)

    dataset_path: Path
    manifest_path: Path
    dataset_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$",
    )


def update_market_data(
    *,
    source: MarketDataSource,
    store: ParquetMarketStore,
    pair: ForexPair,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
) -> DatasetUpdateResult:
    """Fetch and safely merge a new batch into an existing dataset."""

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

    existing_dataset_path = store.dataset_path(
        pair,
        timeframe,
    )

    if existing_dataset_path.exists():
        existing_bars = store.read_bars(
            pair,
            timeframe,
        )
    else:
        existing_bars = []

    incoming_bars = list(
        source.fetch_bars(
            pair=pair,
            timeframe=timeframe,
            start=start_utc,
            end=end_utc,
        )
    )

    if not incoming_bars:
        raise ValueError(
            "The market-data source returned no bars.",
        )

    for bar in incoming_bars:
        if bar.pair != pair:
            raise ValueError(
                "The market-data source returned a different currency pair.",
            )

        if bar.timeframe != timeframe:
            raise ValueError(
                "The market-data source returned a different timeframe.",
            )

        if not start_utc <= bar.timestamp < end_utc:
            raise ValueError(
                "A market bar falls outside the requested time interval.",
            )

    merged_bars = merge_market_bars(
        existing_bars,
        incoming_bars,
    )

    overlapping_bars = (
        len(existing_bars)
        + len(incoming_bars)
        - len(merged_bars)
    )

    new_bars = (
        len(merged_bars)
        - len(existing_bars)
    )

    dataset_path = store.write_bars(
        merged_bars,
        overwrite=existing_dataset_path.exists(),
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

    return DatasetUpdateResult(
        source=source.name,
        pair=pair,
        timeframe=timeframe,
        requested_start=start_utc,
        requested_end=end_utc,
        existing_bars=len(existing_bars),
        fetched_bars=len(incoming_bars),
        overlapping_bars=overlapping_bars,
        new_bars=new_bars,
        total_bars=len(merged_bars),
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        dataset_sha256=manifest.sha256,
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