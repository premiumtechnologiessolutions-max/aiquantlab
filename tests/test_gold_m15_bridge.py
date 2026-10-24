"""CSV bridge roundtrip and invalid-data regression tests."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.gold_m15_to_canonical_csv import export


def _bars() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=3, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "o": [2000, 2001, 2002],
            "h": [2001, 2002, 2003],
            "l": [1999, 2000, 2001],
            "c": [2000, 2001, 2002],
            "ao": [2000.35, 2001.35, 2002.35],
            "ah": [2001.35, 2002.35, 2003.35],
            "al": [1999.35, 2000.35, 2001.35],
            "ac": [2000.35, 2001.35, 2002.35],
            "ts": [15, 15, 15],
        },
        index=idx,
    )


def test_gold_csv_preserves_bid_ask_and_marks_volume_unknown(tmp_path) -> None:
    source = tmp_path / "gold.pkl"
    destination = tmp_path / "gold.csv"
    _bars().to_pickle(source)
    assert export(source, destination, point_size=0.01) == 3
    output = pd.read_csv(destination)
    assert output["tick_volume"].tolist() == [0, 0, 0]
    assert output["spread_points"].tolist() == pytest.approx([35, 35, 35])
    assert output["ask_high"].iloc[1] == pytest.approx(2002.35)
    assert output["source_m1_count"].iloc[0] == 15


def test_gold_csv_rejects_missing_point_and_negative_spread(tmp_path) -> None:
    source = tmp_path / "gold.pkl"
    destination = tmp_path / "gold.csv"
    _bars().to_pickle(source)
    with pytest.raises(ValueError, match="point_size"):
        export(source, destination, point_size=0)
    invalid = _bars()
    invalid.loc[invalid.index[0], "ao"] = 1999.80
    invalid.to_pickle(source)
    with pytest.raises(ValueError, match="Negative bid/ask"):
        export(source, destination, point_size=0.01)
