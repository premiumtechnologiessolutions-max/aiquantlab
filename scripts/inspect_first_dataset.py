from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from statistics import mean

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import (
    DatasetManifest,
    calculate_file_sha256,
)
from ai_quant_lab.data.quality import inspect_market_bars
from ai_quant_lab.data.storage import ParquetMarketStore

PAIR: ForexPair = "EURUSD"
TIMEFRAME: Timeframe = "M15"
DATA_ROOT = Path("data/processed")


def main() -> int:
    """Inspect the first real MetaTrader 5 dataset."""

    store = ParquetMarketStore(DATA_ROOT)

    dataset_path = store.dataset_path(
        PAIR,
        TIMEFRAME,
    )

    manifest_path = (
        DATA_ROOT
        / PAIR
        / TIMEFRAME
        / "manifest.json"
    )

    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}")
        return 1

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        return 1

    bars = store.read_bars(
        PAIR,
        TIMEFRAME,
    )

    if not bars:
        print("Dataset contains no market bars.")
        return 1

    report = inspect_market_bars(bars)

    manifest = DatasetManifest.model_validate_json(
        manifest_path.read_text(
            encoding="utf-8",
        )
    )

    current_sha256 = calculate_file_sha256(
        dataset_path,
    )

    timestamps = [
        bar.timestamp
        for bar in bars
    ]

    strictly_increasing = all(
        current > previous
        for previous, current in pairwise(timestamps)
    )

    average_spread = mean(
        bar.spread_points
        for bar in bars
    )

    minimum_price = min(
        bar.low
        for bar in bars
    )

    maximum_price = max(
        bar.high
        for bar in bars
    )

    print("AI Quant Lab — Dataset Inspection")
    print("=" * 42)
    print(f"Pair: {report.pair}")
    print(f"Timeframe: {report.timeframe}")
    print(f"Bars: {report.bar_count}")
    print(f"First timestamp: {report.first_timestamp}")
    print(f"Last timestamp: {report.last_timestamp}")
    print(f"Minimum price: {minimum_price:.5f}")
    print(f"Maximum price: {maximum_price:.5f}")
    print(f"Average spread points: {average_spread:.2f}")
    print(f"Duplicate timestamps: {report.duplicate_timestamps}")
    print(f"Out-of-order bars: {report.out_of_order_bars}")
    print(f"Missing intervals: {report.missing_intervals}")
    print(f"Strict timestamp order: {strictly_increasing}")
    print()
    print(f"Manifest bars: {manifest.bar_count}")
    print(f"Manifest SHA-256: {manifest.sha256}")
    print(f"Current SHA-256:  {current_sha256}")

    checks = {
        "Dataset structure": report.is_clean,
        "Timestamp ordering": strictly_increasing,
        "Manifest bar count": manifest.bar_count == len(bars),
        "Dataset fingerprint": manifest.sha256 == current_sha256,
    }

    print()
    print("Integrity checks:")

    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"- {check_name}: {status}")

    if not all(checks.values()):
        print()
        print("Dataset inspection failed.")
        return 1

    print()
    print("Dataset inspection completed successfully.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())