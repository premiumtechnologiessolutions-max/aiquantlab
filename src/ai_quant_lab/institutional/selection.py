from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from random import Random

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.institutional.regime_engine import InstitutionalRegime
from ai_quant_lab.strategies import StrategyName


class BanditArmState(BaseModel):
    """Persistent Beta posterior for one strategy in one market context."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    regime: InstitutionalRegime
    strategy_name: StrategyName
    alpha: float = Field(default=1.0, gt=0)
    beta: float = Field(default=1.0, gt=0)
    selections: int = Field(default=0, ge=0)
    observations: int = Field(default=0, ge=0)
    cumulative_reward: float = Field(default=0.0, ge=0)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def posterior_mean(self) -> float:
        """Return the expected normalized Quant Score under the Beta posterior."""

        return self.alpha / (self.alpha + self.beta)


class BanditSelection(BaseModel):
    """Auditable Thompson-sampling decision for one campaign."""

    model_config = ConfigDict(frozen=True)

    pair: ForexPair
    timeframe: Timeframe
    regime: InstitutionalRegime
    strategy_name: StrategyName
    deterministic_seed: str
    sampled_values: dict[str, float]
    posterior_means: dict[str, float]
    selected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BanditUpdate(BaseModel):
    """Idempotent campaign outcome applied to exactly one posterior."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str
    pair: ForexPair
    timeframe: Timeframe
    regime: InstitutionalRegime
    strategy_name: StrategyName
    quant_score: float = Field(ge=0, le=100)
    normalized_reward: float = Field(ge=0, le=1)
    gate_passed: bool
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_reward_matches_score(self) -> "BanditUpdate":
        expected = self.quant_score / 100.0
        if abs(self.normalized_reward - expected) > 1e-12:
            raise ValueError("normalized_reward must equal quant_score / 100.")
        return self


def eligible_strategies(regime: InstitutionalRegime) -> tuple[StrategyName, ...]:
    """Return the constitutionally allowed arms for one detected regime."""

    candidates: dict[InstitutionalRegime, tuple[StrategyName, ...]] = {
        InstitutionalRegime.TRENDING_UP: (
            "time_series_momentum",
            "kalman_adaptive_trend",
            "multi_horizon_vol_trend",
            "donchian_breakout",
        ),
        InstitutionalRegime.TRENDING_DOWN: (
            "time_series_momentum",
            "kalman_adaptive_trend",
            "multi_horizon_vol_trend",
            "donchian_breakout",
        ),
        InstitutionalRegime.MEAN_REVERTING: (
            "kalman_mean_reversion",
            "variance_ratio_regime_switch",
            "zscore_mean_reversion",
        ),
        InstitutionalRegime.HIGH_VOLATILITY: (
            "volatility_breakout",
            "garman_klass_vol_breakout",
            "variance_ratio_regime_switch",
        ),
        InstitutionalRegime.LOW_VOLATILITY: (
            "kalman_mean_reversion",
            "zscore_mean_reversion",
            "variance_ratio_regime_switch",
        ),
        InstitutionalRegime.TRANSITION: (
            "variance_ratio_regime_switch",
            "kalman_adaptive_trend",
        ),
        InstitutionalRegime.LIQUIDITY_STRESS: ("volatility_breakout",),
        InstitutionalRegime.RISK_ON: ("time_series_momentum",),
        InstitutionalRegime.RISK_OFF: ("volatility_breakout",),
        InstitutionalRegime.INSUFFICIENT_DATA: ("buy_and_hold",),
    }

    return candidates[regime]


def thompson_select(
    arms: tuple[BanditArmState, ...],
    *,
    campaign_id: str,
) -> BanditSelection:
    """Choose an arm with reproducible Thompson sampling.

    Thompson sampling is stochastic mathematically. For auditability, this implementation
    seeds an isolated PRNG from immutable campaign/context/posterior state. Replaying the
    same evidence therefore produces the same draw and the same selection.
    """

    if not arms:
        raise ValueError("Thompson sampling requires at least one strategy arm.")

    ordered = tuple(sorted(arms, key=lambda arm: arm.strategy_name))
    context = "|".join(
        (
            campaign_id,
            ordered[0].pair,
            ordered[0].timeframe,
            ordered[0].regime.value,
            *(
                f"{arm.strategy_name}:{arm.alpha:.12f}:{arm.beta:.12f}:{arm.selections}"
                for arm in ordered
            ),
        )
    )
    seed_hex = sha256(context.encode("utf-8")).hexdigest()
    generator = Random(int(seed_hex[:16], 16))
    sampled = {
        arm.strategy_name: generator.betavariate(arm.alpha, arm.beta)
        for arm in ordered
    }
    selected = max(
        ordered,
        key=lambda arm: (
            sampled[arm.strategy_name],
            arm.posterior_mean,
            -arm.selections,
            arm.strategy_name,
        ),
    )

    return BanditSelection(
        pair=selected.pair,
        timeframe=selected.timeframe,
        regime=selected.regime,
        strategy_name=selected.strategy_name,
        deterministic_seed=seed_hex,
        sampled_values=sampled,
        posterior_means={arm.strategy_name: arm.posterior_mean for arm in ordered},
    )


def update_arm(
    arm: BanditArmState,
    *,
    quant_score: float,
) -> BanditArmState:
    """Update a Beta posterior with the normalized deterministic Quant Score."""

    reward = max(0.0, min(1.0, quant_score / 100.0))

    return arm.model_copy(
        update={
            "alpha": arm.alpha + reward,
            "beta": arm.beta + (1.0 - reward),
            "observations": arm.observations + 1,
            "cumulative_reward": arm.cumulative_reward + reward,
            "updated_at": datetime.now(UTC),
        }
    )
