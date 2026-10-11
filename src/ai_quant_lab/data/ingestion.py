from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import (
    build_dataset_manifest,
    write_dataset_manifest,
)
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore


class MarketDataSource(Protocol):
    """Contract that every market-data provider must implement."""

    @property
    def name(self) -> str:
        """Return the unique source name."""

        ...

    def fetch_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Sequence[MarketBar]:
        """Fetch market bars within the requested UTC interval."""

        ...


class IngestionResult(BaseModel):
    """Immutable result produced after successfully ingesting a dataset."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    pair: ForexPair
    timeframe: Timeframe

    requested_start: datetime
    requested_end: datetime

    bars_written: int = Field(gt=0)
    missing_intervals: int = Field(ge=0)

    dataset_path: Path
    manifest_path: Path
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def ingest_market_data(
    *,
    source: MarketDataSource,
    store: ParquetMarketStore,
    pair: ForexPair,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    overwrite: bool = False,
) -> IngestionResult:
    """Fetch, validate, store, and fingerprint one market dataset."""

    start_utc = _normalize_boundary(start, name="start")
    end_utc = _normalize_boundary(end, name="end")

    if start_utc >= end_utc:
        raise ValueError("Start time must be earlier than end time.")

    bars = list(
        source.fetch_bars(
            pair=pair,
            timeframe=timeframe,
            start=start_utc,
            end=end_utc,
        )
    )

    if not bars:
        raise ValueError("The market-data source returned no bars.")

    for bar in bars:
        if not start_utc <= bar.timestamp < end_utc:
            raise ValueError(
                "A market bar falls outside the requested time interval.",
            )

    dataset_path = store.write_bars(
        bars,
        overwrite=overwrite,
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

    return IngestionResult(
        source=source.name,
        pair=pair,
        timeframe=timeframe,
        requested_start=start_utc,
        requested_end=end_utc,
        bars_written=manifest.bar_count,
        missing_intervals=manifest.missing_intervals,
        dataset_path=dataset_path,
        manifest_path=manifest_path,
        dataset_sha256=manifest.sha256,
    )


def _normalize_boundary(
    value: datetime,
    *,
    name: str,
) -> datetime:
    """Require a timezone-aware boundary and normalize it to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"The {name} time must include timezone information.",
        )

    return value.astimezone(UTC)