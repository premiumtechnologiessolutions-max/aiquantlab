from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TradingMode = Literal["research", "shadow", "paper"]

ForexPair = Literal[
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "USDCAD",
    "AUDUSD",
    "NZDUSD",
    "XAUUSD",  # Gold spot: quote currency is USD per troy ounce, NOT an FX pip.
]

Timeframe = Literal["M1", "M5", "M15", "H1", "H4", "D1"]


class ProjectConfig(BaseModel):
    """Validated configuration shared by all project components."""

    project_name: str = Field(min_length=1)
    mode: TradingMode
    timezone: Literal["UTC"]
    data_dir: Path
    pairs: tuple[ForexPair, ...]
    timeframes: tuple[Timeframe, ...]

    @field_validator("pairs")
    @classmethod
    def pairs_must_be_unique(
        cls,
        pairs: tuple[ForexPair, ...],
    ) -> tuple[ForexPair, ...]:
        if len(pairs) != len(set(pairs)):
            raise ValueError("Currency pairs must be unique.")

        return pairs

    @field_validator("timeframes")
    @classmethod
    def timeframes_must_be_unique(
        cls,
        timeframes: tuple[Timeframe, ...],
    ) -> tuple[Timeframe, ...]:
        if len(timeframes) != len(set(timeframes)):
            raise ValueError("Timeframes must be unique.")

        return timeframes


def load_config(
    path: str | Path = "configs/base.toml",
) -> ProjectConfig:
    """Load and validate the project configuration."""

    config_path = Path(path)

    with config_path.open("rb") as stream:
        data = tomllib.load(stream)

    return ProjectConfig.model_validate(data)
