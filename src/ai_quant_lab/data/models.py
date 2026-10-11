from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_quant_lab.config import ForexPair, Timeframe


class MarketBar(BaseModel):
    """Canonical validated OHLC market bar used across the project."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    timestamp: datetime

    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)

    tick_volume: int = Field(ge=0)
    real_volume: float | None = Field(default=None, ge=0)
    spread_points: float = Field(ge=0)

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include timezone information.")

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ohlc_structure(self) -> MarketBar:
        if self.low > self.high:
            raise ValueError("Low price cannot be greater than high price.")

        if self.high < max(self.open, self.close):
            raise ValueError("High must be greater than or equal to open and close.")

        if self.low > min(self.open, self.close):
            raise ValueError("Low must be less than or equal to open and close.")

        return self