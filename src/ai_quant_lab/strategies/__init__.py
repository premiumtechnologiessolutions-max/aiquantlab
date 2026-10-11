"""Causal strategies available to the AI Quant Lab research engine."""

from ai_quant_lab.strategies.advanced import (
    GarmanKlassVolatilityBreakout,
    KalmanAdaptiveTrend,
    MultiHorizonVolatilityTrend,
    VarianceRatioRegimeSwitch,
)
from ai_quant_lab.strategies.base import (
    PositionSignal,
    ResearchStrategy,
    StrategyDescriptor,
    StrategyFamily,
)
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
from ai_quant_lab.strategies.catalog import (
    STRATEGY_CATALOG,
    SUPPORTED_STRATEGIES,
    StrategyName,
    StrategySpecification,
    build_strategy,
    neighboring_variants,
    normalize_strategy_name,
)
from ai_quant_lab.strategies.institutional import (
    CointegrationDiagnostics,
    KalmanMeanReversion,
    RiskParityAllocation,
    TimeSeriesMomentum,
    VolatilityBreakout,
    analyze_cointegration_pair,
    inverse_volatility_risk_parity,
)

__all__ = [
    "STRATEGY_CATALOG",
    "SUPPORTED_STRATEGIES",
    "BollingerBandReversion",
    "BuyAndHold",
    "CointegrationDiagnostics",
    "DonchianBreakout",
    "ExponentialMovingAverageCrossover",
    "GarmanKlassVolatilityBreakout",
    "KalmanAdaptiveTrend",
    "KalmanMeanReversion",
    "MovingAverageConvergenceDivergence",
    "MovingAverageCrossover",
    "MultiHorizonVolatilityTrend",
    "PositionSignal",
    "RateOfChangeMomentum",
    "RelativeStrengthIndexReversion",
    "ResearchStrategy",
    "RiskParityAllocation",
    "StrategyDescriptor",
    "StrategyFamily",
    "StrategyName",
    "StrategySpecification",
    "TimeSeriesMomentum",
    "VarianceRatioRegimeSwitch",
    "VolatilityBreakout",
    "ZScoreMeanReversion",
    "analyze_cointegration_pair",
    "build_strategy",
    "inverse_volatility_risk_parity",
    "neighboring_variants",
    "normalize_strategy_name",
]
