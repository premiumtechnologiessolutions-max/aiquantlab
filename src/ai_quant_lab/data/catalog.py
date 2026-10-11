from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.quality import inspect_market_bars
from ai_quant_lab.data.storage import ParquetMarketStore


class DatasetManifest(BaseModel):
    """Reproducible identity and metadata for one market dataset."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    pair: ForexPair
    timeframe: Timeframe

    bar_count: int = Field(gt=0)
    first_timestamp: datetime
    last_timestamp: datetime
    missing_intervals: int = Field(ge=0)

    file_size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1)


def calculate_file_sha256(path: Path) -> str:
    """Calculate the SHA-256 fingerprint of a file."""

    digest = sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def build_dataset_manifest(
    store: ParquetMarketStore,
    pair: ForexPair,
    timeframe: Timeframe,
) -> DatasetManifest:
    """Build a reproducible manifest for an existing dataset."""

    path = store.dataset_path(pair, timeframe)
    bars = store.read_bars(pair, timeframe)
    report = inspect_market_bars(bars)

    return DatasetManifest(
        pair=pair,
        timeframe=timeframe,
        bar_count=report.bar_count,
        first_timestamp=report.first_timestamp,
        last_timestamp=report.last_timestamp,
        missing_intervals=report.missing_intervals,
        file_size_bytes=path.stat().st_size,
        sha256=calculate_file_sha256(path),
        relative_path=path.relative_to(store.root).as_posix(),
    )


def write_dataset_manifest(
    manifest: DatasetManifest,
    root: str | Path = "data/processed",
) -> Path:
    """Atomically write a dataset manifest beside its Parquet file."""

    manifest_path = (
        Path(root)
        / manifest.pair
        / manifest.timeframe
        / "manifest.json"
    )

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = manifest_path.with_suffix(".temporary.json")

    temporary_path.write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )

    temporary_path.replace(manifest_path)

    return manifest_path