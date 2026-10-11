from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_quant_lab.backtesting import BacktestMetrics
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.experiments import StrategyLifecycle
from ai_quant_lab.regimes import MarketRegime


class ProbabilisticForecast(BaseModel):
    """Calibratable scenario forecast that never claims certainty."""

    model_config = ConfigDict(frozen=True)

    issued_at: datetime
    horizon_bars: int = Field(ge=1)
    probability_up: float = Field(ge=0, le=1)
    probability_down: float = Field(ge=0, le=1)
    probability_range: float = Field(ge=0, le=1)
    expected_return: float
    expected_volatility: float = Field(ge=0)
    regime: MarketRegime
    confidence: float = Field(ge=0, le=1)
    data_quality_score: float = Field(ge=0, le=1)
    supporting_reasons: tuple[str, ...]
    opposing_reasons: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    model_version: str

    @model_validator(mode="after")
    def probabilities_must_sum_to_one(self) -> ProbabilisticForecast:
        """Require an internally coherent probability distribution."""

        total = self.probability_up + self.probability_down + self.probability_range

        if abs(total - 1.0) > 1e-6:
            raise ValueError("Forecast probabilities must sum to one.")

        return self


class StrategyEvidence(BaseModel):
    """One strategy version and its latest immutable evidence in a pair profile."""

    model_config = ConfigDict(frozen=True)

    strategy_version_id: str
    status: StrategyLifecycle
    metrics: BacktestMetrics
    experiment_id: str
    reason: str


class PairIntelligenceProfile(BaseModel):
    """Versioned, persistent state for one pair and timeframe."""

    model_config = ConfigDict(frozen=True)

    profile_id: str
    pair: ForexPair
    timeframe: Timeframe
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    latest_regime: MarketRegime
    dominant_regime: MarketRegime
    champion_version_id: str | None = None
    challenger_version_ids: tuple[str, ...] = ()
    strategy_evidence: tuple[StrategyEvidence, ...] = ()
    forecast: ProbabilisticForecast | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PairIntelligenceStore:
    """Artifact store that preserves every profile snapshot and a latest pointer."""

    def __init__(self, root: str | Path = "data/intelligence") -> None:
        self.root = Path(root)

    def write(self, profile: PairIntelligenceProfile) -> Path:
        """Persist a new immutable profile snapshot without deleting history."""

        directory = self.root / profile.pair / profile.timeframe
        directory.mkdir(parents=True, exist_ok=True)
        snapshot_path = directory / f"{profile.profile_id}.json"

        if snapshot_path.exists():
            existing = PairIntelligenceProfile.model_validate_json(
                snapshot_path.read_text(encoding="utf-8")
            )

            if existing != profile:
                raise FileExistsError(
                    f"Profile ID '{profile.profile_id}' already has different content."
                )
        else:
            _atomic_write(snapshot_path, profile.model_dump_json(indent=2))

        latest_path = directory / "latest.json"
        _atomic_write(
            latest_path,
            json.dumps(
                {
                    "profile_id": profile.profile_id,
                    "snapshot": snapshot_path.name,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                indent=2,
            ),
        )

        return snapshot_path

    def latest(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
    ) -> PairIntelligenceProfile:
        """Load the latest persisted profile for one pair and timeframe."""

        directory = self.root / pair / timeframe
        pointer_path = directory / "latest.json"

        if not pointer_path.exists():
            raise FileNotFoundError(f"No intelligence profile exists for {pair} {timeframe}.")

        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        snapshot_path = directory / str(pointer["snapshot"])

        return PairIntelligenceProfile.model_validate_json(
            snapshot_path.read_text(encoding="utf-8")
        )


def _atomic_write(path: Path, content: str) -> None:
    """Write one UTF-8 artifact through an atomic sibling rename."""

    temporary = path.with_suffix(path.suffix + ".temporary")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
