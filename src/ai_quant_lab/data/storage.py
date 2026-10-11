from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.quality import inspect_market_bars

MARKET_BAR_SCHEMA = pa.schema(
    [
        pa.field("pair", pa.string(), nullable=False),
        pa.field("timeframe", pa.string(), nullable=False),
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("tick_volume", pa.int64(), nullable=False),
        pa.field("real_volume", pa.float64(), nullable=True),
        pa.field("spread_points", pa.float64(), nullable=False),
    ]
)


class ParquetMarketStore:
    """Store and retrieve validated market bars in Parquet format."""

    def __init__(
        self,
        root: str | Path = "data/processed",
    ) -> None:
        self.root = Path(root)

    def dataset_path(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
    ) -> Path:
        """Return the canonical storage path for a dataset."""

        return self.root / pair / timeframe / "bars.parquet"

    def write_bars(
        self,
        bars: Sequence[MarketBar],
        *,
        overwrite: bool = False,
    ) -> Path:
        """Validate and atomically store market bars."""

        if not bars:
            raise ValueError("At least one market bar is required.")

        report = inspect_market_bars(bars)

        if not report.is_clean:
            raise ValueError(
                "Market bars must be clean before they can be stored.",
            )

        path = self.dataset_path(
            pair=report.pair,
            timeframe=report.timeframe,
        )

        if path.exists() and not overwrite:
            raise FileExistsError(
                f"Dataset already exists: {path}",
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        rows = [
            bar.model_dump(mode="python")
            for bar in bars
        ]

        table = pa.Table.from_pylist(
            rows,
            schema=MARKET_BAR_SCHEMA,
        )

        temporary_path = path.with_suffix(".temporary.parquet")

        pq.write_table(
            table,
            temporary_path,
            compression="zstd",
        )

        temporary_path.replace(path)

        return path

    def read_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
    ) -> list[MarketBar]:
        """Read canonical market bars from Parquet storage."""

        path = self.dataset_path(
            pair=pair,
            timeframe=timeframe,
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Dataset does not exist: {path}",
            )

        table = pq.read_table(path)

        return [
            MarketBar.model_validate(row)
            for row in table.to_pylist()
        ]