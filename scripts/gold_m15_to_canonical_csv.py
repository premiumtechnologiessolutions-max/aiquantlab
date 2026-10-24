"""Export the user's audited XAUUSD M15 bid/ask cache to AI Quant Lab CSV.

The cache must come from a trusted local source; Python pickle must NEVER be
loaded from arbitrary/untrusted attachments. Tick volume is unknown, not zero
actual transactions. Ask OHLC is retained as extra columns for bid/ask studies.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def export(source: Path, destination: Path, *, point_size: float) -> int:
    """Prepare validated bar rows, requiring an explicit broker price increment."""
    if not np.isfinite(point_size) or point_size <= 0:
        raise ValueError("point_size must be positive and broker verified.")

    bars = pd.read_pickle(source)  # only use with a TRUSTED local cache
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("Gold cache requires timezone-aware timestamps.")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("Gold timestamps must be strictly ascending and unique.")

    columns = ("o", "h", "l", "c", "ao", "ah", "al", "ac")
    if not set(columns).issubset(bars.columns):
        raise ValueError("Missing separate bid/ask OHLC columns.")
    values = bars[list(columns)]
    if not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any():
        raise ValueError("Invalid quote price.")
    if (bars.ao < bars.o).any() or (bars.ac < bars.c).any():
        raise ValueError("Negative bid/ask spread.")
    if (bars.l > bars[["o", "c"]].min(axis=1)).any() or (
        bars.h < bars[["o", "c"]].max(axis=1)
    ).any():
        raise ValueError("Invalid bid OHLC envelope.")
    if (bars.al > bars[["ao", "ac"]].min(axis=1)).any() or (
        bars.ah < bars[["ao", "ac"]].max(axis=1)
    ).any():
        raise ValueError("Invalid ask OHLC envelope.")

    # Core CSV ingestion requires tick_volume even when unavailable.
    # 0 is a documented UNKNOWN sentinel, NOT an observation of no ticks.
    quotes = pd.DataFrame(
        {
            "timestamp": bars.index.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "open": bars.o.to_numpy(),
            "high": bars.h.to_numpy(),
            "low": bars.l.to_numpy(),
            "close": bars.c.to_numpy(),
            "tick_volume": np.zeros(len(bars), dtype=np.int64),
            "spread_points": ((bars.ao - bars.o) / point_size).round(8).to_numpy(),
            "ask_open": bars.ao.to_numpy(),
            "ask_high": bars.ah.to_numpy(),
            "ask_low": bars.al.to_numpy(),
            "ask_close": bars.ac.to_numpy(),
            "source_m1_count": bars.ts.to_numpy() if "ts" in bars else np.zeros(len(bars)),
        }
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    quotes.to_csv(destination, index=False, float_format="%.8f")
    return len(quotes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export XAUUSD M15 bid/ask to CSV")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--point-size", type=float, required=True)
    args = parser.parse_args()
    count = export(args.source, args.destination, point_size=args.point_size)
    print(f"Exported {count} M15 bars; tick_volume=0 means unknown.")


if __name__ == "__main__":
    main()
