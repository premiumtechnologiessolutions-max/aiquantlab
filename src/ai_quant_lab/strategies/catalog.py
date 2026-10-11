from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast, get_args

from pydantic import BaseModel, ConfigDict

from ai_quant_lab.strategies.advanced import (
    GarmanKlassVolatilityBreakout,
    KalmanAdaptiveTrend,
    MultiHorizonVolatilityTrend,
    VarianceRatioRegimeSwitch,
)
from ai_quant_lab.strategies.base import ResearchStrategy, StrategyFamily
from ai_quant_lab.strategies.builtin import (
    BollingerBandReversion,
    BuyAndHold,
    DonchianBreakout,
    ExponentialMovingAverageCrossover,
    MovingAverageConvergenceDivergence,
    MovingAverageCrossover,
    RateOfChangeMomentum,
    RelativeStrengthIndexReversion,
    ZScoreMeanReversion,
)
from ai_quant_lab.strategies.institutional import (
    KalmanMeanReversion,
    TimeSeriesMomentum,
    VolatilityBreakout,
)

StrategyName = Literal[
    "moving_average_crossover",
    "ema_crossover",
    "macd_momentum",
    "roc_momentum",
    "donchian_breakout",
    "zscore_mean_reversion",
    "rsi_mean_reversion",
    "bollinger_reversion",
    "kalman_adaptive_trend",
    "multi_horizon_vol_trend",
    "variance_ratio_regime_switch",
    "garman_klass_vol_breakout",
    "time_series_momentum",
    "kalman_mean_reversion",
    "volatility_breakout",
    "buy_and_hold",
]
StrategyParameter = int | float | str
SUPPORTED_STRATEGIES: tuple[StrategyName, ...] = cast(
    tuple[StrategyName, ...],
    get_args(StrategyName),
)


class StrategySpecification(BaseModel):
    """Human-readable catalog entry for one reproducible strategy."""

    model_config = ConfigDict(frozen=True)

    name: StrategyName
    family: StrategyFamily
    description: str
    default_parameters: dict[str, StrategyParameter]
    research_tier: Literal["foundation", "advanced"] = "foundation"
    data_requirements: str = "single_asset_ohlcv"


STRATEGY_CATALOG: tuple[StrategySpecification, ...] = (
    StrategySpecification(
        name="moving_average_crossover",
        family=StrategyFamily.TREND,
        description="Simple moving-average trend following.",
        default_parameters={"fast_window": 20, "slow_window": 50},
    ),
    StrategySpecification(
        name="ema_crossover",
        family=StrategyFamily.TREND,
        description="Faster exponentially weighted trend following.",
        default_parameters={"fast_window": 12, "slow_window": 26},
    ),
    StrategySpecification(
        name="macd_momentum",
        family=StrategyFamily.MOMENTUM,
        description="MACD line versus signal-line momentum.",
        default_parameters={"fast_window": 12, "slow_window": 26, "signal_window": 9},
    ),
    StrategySpecification(
        name="roc_momentum",
        family=StrategyFamily.MOMENTUM,
        description="Rate-of-change momentum with a neutral threshold.",
        default_parameters={"window": 12, "threshold_percent": 0.1},
    ),
    StrategySpecification(
        name="donchian_breakout",
        family=StrategyFamily.BREAKOUT,
        description="Prior-channel high and low breakout.",
        default_parameters={"window": 20},
    ),
    StrategySpecification(
        name="zscore_mean_reversion",
        family=StrategyFamily.MEAN_REVERSION,
        description="Rolling z-score mean reversion.",
        default_parameters={"window": 30, "entry_z": 1.5, "exit_z": 0.25},
    ),
    StrategySpecification(
        name="rsi_mean_reversion",
        family=StrategyFamily.MEAN_REVERSION,
        description="RSI extreme entries with midpoint exits.",
        default_parameters={
            "window": 14,
            "oversold": 30.0,
            "overbought": 70.0,
            "exit_level": 50.0,
        },
    ),
    StrategySpecification(
        name="bollinger_reversion",
        family=StrategyFamily.VOLATILITY,
        description="Volatility-band mean reversion.",
        default_parameters={"window": 20, "standard_deviations": 2.0},
    ),
    StrategySpecification(
        name="kalman_adaptive_trend",
        family=StrategyFamily.ADAPTIVE,
        description="State-space latent trend with volatility-normalized slope.",
        default_parameters={
            "warmup": 32,
            "volatility_window": 32,
            "process_noise": 1e-8,
            "measurement_noise": 1e-5,
            "signal_threshold": 0.15,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="multi_horizon_vol_trend",
        family=StrategyFamily.ADAPTIVE,
        description="Multi-horizon trend scores scaled by trailing realized volatility.",
        default_parameters={
            "short_horizon": 8,
            "medium_horizon": 32,
            "long_horizon": 96,
            "volatility_window": 32,
            "signal_threshold": 0.75,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="variance_ratio_regime_switch",
        family=StrategyFamily.STATISTICAL,
        description="Variance-ratio persistence test switching trend and reversion logic.",
        default_parameters={
            "window": 80,
            "aggregation_lag": 4,
            "regime_threshold": 0.08,
            "zscore_window": 20,
            "entry_z": 1.25,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="garman_klass_vol_breakout",
        family=StrategyFamily.VOLATILITY,
        description="OHLC range-volatility shock breakout using prior bars only.",
        default_parameters={
            "window": 30,
            "entry_multiplier": 1.5,
            "exit_multiplier": 0.35,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="time_series_momentum",
        family=StrategyFamily.MOMENTUM,
        description="Volatility-scaled time-series momentum with a causal dead zone.",
        default_parameters={
            "horizon": 96,
            "volatility_window": 32,
            "entry_score": 0.8,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="kalman_mean_reversion",
        family=StrategyFamily.MEAN_REVERSION,
        description="Standardized residual reversion around a local-level Kalman estimate.",
        default_parameters={
            "warmup": 40,
            "residual_window": 40,
            "entry_z": 1.75,
            "exit_z": 0.35,
            "process_noise": 1e-7,
            "measurement_noise": 1e-5,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="volatility_breakout",
        family=StrategyFamily.VOLATILITY,
        description="Realized-volatility adaptive price-channel breakout.",
        default_parameters={
            "window": 40,
            "volatility_window": 20,
            "entry_multiplier": 1.25,
            "exit_multiplier": 0.25,
        },
        research_tier="advanced",
    ),
    StrategySpecification(
        name="buy_and_hold",
        family=StrategyFamily.BASELINE,
        description="Long-only research baseline.",
        default_parameters={},
    ),
)


def normalize_strategy_name(value: str) -> StrategyName:
    """Normalize and validate a catalog strategy name."""

    normalized = value.strip().casefold().replace("-", "_")

    if normalized not in SUPPORTED_STRATEGIES:
        supported = ", ".join(SUPPORTED_STRATEGIES)
        raise ValueError(f"Unsupported strategy '{value}'. Supported strategies: {supported}.")

    return normalized


def build_strategy(
    name: StrategyName,
    parameters: Mapping[str, StrategyParameter] | None = None,
) -> ResearchStrategy:
    """Construct one catalog strategy with validated declared parameters."""

    resolved = dict(_specification(name).default_parameters)
    resolved.update(parameters or {})

    if name == "moving_average_crossover":
        return MovingAverageCrossover(
            fast_window=_integer(resolved, "fast_window"),
            slow_window=_integer(resolved, "slow_window"),
        )

    if name == "ema_crossover":
        return ExponentialMovingAverageCrossover(
            fast_window=_integer(resolved, "fast_window"),
            slow_window=_integer(resolved, "slow_window"),
        )

    if name == "macd_momentum":
        return MovingAverageConvergenceDivergence(
            fast_window=_integer(resolved, "fast_window"),
            slow_window=_integer(resolved, "slow_window"),
            signal_window=_integer(resolved, "signal_window"),
        )

    if name == "roc_momentum":
        return RateOfChangeMomentum(
            window=_integer(resolved, "window"),
            threshold_percent=_number(resolved, "threshold_percent"),
        )

    if name == "donchian_breakout":
        return DonchianBreakout(window=_integer(resolved, "window"))

    if name == "zscore_mean_reversion":
        return ZScoreMeanReversion(
            window=_integer(resolved, "window"),
            entry_z=_number(resolved, "entry_z"),
            exit_z=_number(resolved, "exit_z"),
        )

    if name == "rsi_mean_reversion":
        return RelativeStrengthIndexReversion(
            window=_integer(resolved, "window"),
            oversold=_number(resolved, "oversold"),
            overbought=_number(resolved, "overbought"),
            exit_level=_number(resolved, "exit_level"),
        )

    if name == "bollinger_reversion":
        return BollingerBandReversion(
            window=_integer(resolved, "window"),
            standard_deviations=_number(resolved, "standard_deviations"),
        )

    if name == "kalman_adaptive_trend":
        return KalmanAdaptiveTrend(
            warmup=_integer(resolved, "warmup"),
            volatility_window=_integer(resolved, "volatility_window"),
            process_noise=_number(resolved, "process_noise"),
            measurement_noise=_number(resolved, "measurement_noise"),
            signal_threshold=_number(resolved, "signal_threshold"),
        )

    if name == "multi_horizon_vol_trend":
        return MultiHorizonVolatilityTrend(
            short_horizon=_integer(resolved, "short_horizon"),
            medium_horizon=_integer(resolved, "medium_horizon"),
            long_horizon=_integer(resolved, "long_horizon"),
            volatility_window=_integer(resolved, "volatility_window"),
            signal_threshold=_number(resolved, "signal_threshold"),
        )

    if name == "variance_ratio_regime_switch":
        return VarianceRatioRegimeSwitch(
            window=_integer(resolved, "window"),
            aggregation_lag=_integer(resolved, "aggregation_lag"),
            regime_threshold=_number(resolved, "regime_threshold"),
            zscore_window=_integer(resolved, "zscore_window"),
            entry_z=_number(resolved, "entry_z"),
        )

    if name == "garman_klass_vol_breakout":
        return GarmanKlassVolatilityBreakout(
            window=_integer(resolved, "window"),
            entry_multiplier=_number(resolved, "entry_multiplier"),
            exit_multiplier=_number(resolved, "exit_multiplier"),
        )

    if name == "time_series_momentum":
        return TimeSeriesMomentum(
            horizon=_integer(resolved, "horizon"),
            volatility_window=_integer(resolved, "volatility_window"),
            entry_score=_number(resolved, "entry_score"),
        )

    if name == "kalman_mean_reversion":
        return KalmanMeanReversion(
            warmup=_integer(resolved, "warmup"),
            residual_window=_integer(resolved, "residual_window"),
            entry_z=_number(resolved, "entry_z"),
            exit_z=_number(resolved, "exit_z"),
            process_noise=_number(resolved, "process_noise"),
            measurement_noise=_number(resolved, "measurement_noise"),
        )

    if name == "volatility_breakout":
        return VolatilityBreakout(
            window=_integer(resolved, "window"),
            volatility_window=_integer(resolved, "volatility_window"),
            entry_multiplier=_number(resolved, "entry_multiplier"),
            exit_multiplier=_number(resolved, "exit_multiplier"),
        )

    return BuyAndHold()


def neighboring_variants(
    name: StrategyName,
    parameters: Mapping[str, StrategyParameter] | None = None,
) -> tuple[ResearchStrategy, ...]:
    """Return a small declared neighborhood for parameter-stability checks."""

    base = build_strategy(name, parameters)
    values = base.descriptor.parameters

    if name in {"moving_average_crossover", "ema_crossover"}:
        fast = _integer(values, "fast_window")
        slow = _integer(values, "slow_window")
        delta_fast = max(1, fast // 5)
        delta_slow = max(1, slow // 5)
        return (
            base,
            build_strategy(
                name,
                {"fast_window": max(2, fast - delta_fast), "slow_window": slow},
            ),
            build_strategy(
                name,
                {"fast_window": fast + delta_fast, "slow_window": slow + delta_slow},
            ),
        )

    if name == "macd_momentum":
        fast = _integer(values, "fast_window")
        slow = _integer(values, "slow_window")
        signal = _integer(values, "signal_window")
        return (
            base,
            build_strategy(
                name,
                {
                    "fast_window": max(2, fast - 2),
                    "slow_window": max(fast + 1, slow - 2),
                    "signal_window": max(2, signal - 1),
                },
            ),
            build_strategy(
                name,
                {
                    "fast_window": fast + 2,
                    "slow_window": slow + 2,
                    "signal_window": signal + 1,
                },
            ),
        )

    if name in {"roc_momentum", "donchian_breakout"}:
        window = _integer(values, "window")
        delta = max(1, window // 5)
        variants: list[ResearchStrategy] = [
            base,
            build_strategy(name, {**values, "window": max(2, window - delta)}),
            build_strategy(name, {**values, "window": window + delta}),
        ]
        return tuple(variants)

    if name == "zscore_mean_reversion":
        window = _integer(values, "window")
        entry = _number(values, "entry_z")
        exit_value = _number(values, "exit_z")
        delta = max(1, window // 5)
        return (
            base,
            build_strategy(
                name,
                {
                    "window": max(3, window - delta),
                    "entry_z": max(exit_value + 0.1, entry - 0.2),
                    "exit_z": exit_value,
                },
            ),
            build_strategy(
                name,
                {"window": window + delta, "entry_z": entry + 0.2, "exit_z": exit_value},
            ),
        )

    if name == "rsi_mean_reversion":
        window = _integer(values, "window")
        return (
            base,
            build_strategy(name, {**values, "window": max(2, window - 2)}),
            build_strategy(name, {**values, "window": window + 2}),
        )

    if name == "bollinger_reversion":
        window = _integer(values, "window")
        deviations = _number(values, "standard_deviations")
        return (
            base,
            build_strategy(
                name,
                {"window": max(3, window - 3), "standard_deviations": max(0.5, deviations - 0.2)},
            ),
            build_strategy(
                name,
                {"window": window + 3, "standard_deviations": deviations + 0.2},
            ),
        )

    if name == "kalman_adaptive_trend":
        threshold = _number(values, "signal_threshold")
        return (
            base,
            build_strategy(name, {**values, "signal_threshold": max(0.01, threshold - 0.05)}),
            build_strategy(name, {**values, "signal_threshold": threshold + 0.05}),
        )

    if name == "multi_horizon_vol_trend":
        threshold = _number(values, "signal_threshold")
        return (
            base,
            build_strategy(name, {**values, "signal_threshold": max(0.1, threshold - 0.15)}),
            build_strategy(name, {**values, "signal_threshold": threshold + 0.15}),
        )

    if name == "variance_ratio_regime_switch":
        threshold = _number(values, "regime_threshold")
        return (
            base,
            build_strategy(name, {**values, "regime_threshold": max(0.01, threshold - 0.02)}),
            build_strategy(name, {**values, "regime_threshold": threshold + 0.02}),
        )

    if name == "garman_klass_vol_breakout":
        multiplier = _number(values, "entry_multiplier")
        exit_multiplier = _number(values, "exit_multiplier")
        return (
            base,
            build_strategy(
                name,
                {
                    **values,
                    "entry_multiplier": max(exit_multiplier + 0.1, multiplier - 0.2),
                },
            ),
            build_strategy(name, {**values, "entry_multiplier": multiplier + 0.2}),
        )

    if name == "time_series_momentum":
        horizon = _integer(values, "horizon")
        score = _number(values, "entry_score")
        return (
            base,
            build_strategy(
                name,
                {
                    **values,
                    "horizon": max(3, horizon - max(2, horizon // 6)),
                    "entry_score": max(0.1, score - 0.15),
                },
            ),
            build_strategy(
                name,
                {
                    **values,
                    "horizon": horizon + max(2, horizon // 6),
                    "entry_score": score + 0.15,
                },
            ),
        )

    if name == "kalman_mean_reversion":
        entry = _number(values, "entry_z")
        residual_window = _integer(values, "residual_window")
        return (
            base,
            build_strategy(
                name,
                {
                    **values,
                    "residual_window": max(10, residual_window - 6),
                    "entry_z": max(0.5, entry - 0.2),
                },
            ),
            build_strategy(
                name,
                {
                    **values,
                    "residual_window": residual_window + 6,
                    "entry_z": entry + 0.2,
                },
            ),
        )

    if name == "volatility_breakout":
        multiplier = _number(values, "entry_multiplier")
        window = _integer(values, "window")
        return (
            base,
            build_strategy(
                name,
                {
                    **values,
                    "window": max(10, window - 6),
                    "entry_multiplier": max(0.2, multiplier - 0.15),
                },
            ),
            build_strategy(
                name,
                {
                    **values,
                    "window": window + 6,
                    "entry_multiplier": multiplier + 0.15,
                },
            ),
        )

    return (base,)


def _specification(name: StrategyName) -> StrategySpecification:
    for specification in STRATEGY_CATALOG:
        if specification.name == name:
            return specification

    raise AssertionError(f"Catalog is missing strategy '{name}'.")


def _integer(values: Mapping[str, StrategyParameter], key: str) -> int:
    value = values[key]

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Strategy parameter '{key}' must be an integer.")

    integer = int(value)

    if float(value) != integer:
        raise ValueError(f"Strategy parameter '{key}' must be an integer.")

    return integer


def _number(values: Mapping[str, StrategyParameter], key: str) -> float:
    value = values[key]

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Strategy parameter '{key}' must be numeric.")

    return float(value)
