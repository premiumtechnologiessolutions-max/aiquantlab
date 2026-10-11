"""Explainable, trailing-window market regime detection."""

from ai_quant_lab.regimes.detector import (
    MarketRegime,
    RegimeChangePoint,
    RegimePoint,
    RegimeSummary,
    detect_change_points,
    detect_market_regimes,
)

__all__ = [
    "MarketRegime",
    "RegimeChangePoint",
    "RegimePoint",
    "RegimeSummary",
    "detect_change_points",
    "detect_market_regimes",
]
