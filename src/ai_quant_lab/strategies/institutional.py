from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import log, sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies.base import (
    PositionSignal,
    StrategyDescriptor,
    StrategyFamily,
    validate_strategy_bars,
)


class TimeSeriesMomentum:
    """Volatility-scaled time-series momentum with a causal dead zone."""

    def __init__(
        self,
        *,
        horizon: int = 96,
        volatility_window: int = 32,
        entry_score: float = 0.8,
    ) -> None:
        if horizon < 3:
            raise ValueError("TSMOM horizon must contain at least three bars.")
        if volatility_window < 3:
            raise ValueError("TSMOM volatility window must contain at least three bars.")
        if entry_score <= 0:
            raise ValueError("TSMOM entry score must be positive.")
        self.horizon = horizon
        self.volatility_window = volatility_window
        self.entry_score = entry_score

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="time_series_momentum",
            family=StrategyFamily.MOMENTUM,
            parameters={
                "horizon": self.horizon,
                "volatility_window": self.volatility_window,
                "entry_score": self.entry_score,
            },
        )

    def generate_signals(self, bars: Sequence[MarketBar]) -> tuple[PositionSignal, ...]:
        validate_strategy_bars(bars)
        prices = [log(bar.close) for bar in bars]
        warmup = max(self.horizon, self.volatility_window)
        signals: list[PositionSignal] = []

        for index in range(len(bars)):
            if index < warmup:
                signals.append(PositionSignal.FLAT)
                continue

            returns = [
                prices[position] - prices[position - 1]
                for position in range(index - self.volatility_window + 1, index + 1)
            ]
            volatility = sqrt(sum(value * value for value in returns) / len(returns))
            score = (prices[index] - prices[index - self.horizon]) / max(
                1e-12, volatility * sqrt(self.horizon)
            )

            if score > self.entry_score:
                signals.append(PositionSignal.LONG)
            elif score < -self.entry_score:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class KalmanMeanReversion:
    """Trade standardized residuals around a causal local-level Kalman estimate."""

    def __init__(
        self,
        *,
        warmup: int = 40,
        residual_window: int = 40,
        entry_z: float = 1.75,
        exit_z: float = 0.35,
        process_noise: float = 1e-7,
        measurement_noise: float = 1e-5,
    ) -> None:
        if warmup < 10 or residual_window < 5:
            raise ValueError("Kalman reversion windows are too short.")
        if entry_z <= 0 or exit_z < 0 or exit_z >= entry_z:
            raise ValueError("Kalman reversion z thresholds are invalid.")
        if process_noise <= 0 or measurement_noise <= 0:
            raise ValueError("Kalman reversion noise variances must be positive.")
        self.warmup = warmup
        self.residual_window = residual_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="kalman_mean_reversion",
            family=StrategyFamily.MEAN_REVERSION,
            parameters={
                "warmup": self.warmup,
                "residual_window": self.residual_window,
                "entry_z": self.entry_z,
                "exit_z": self.exit_z,
                "process_noise": self.process_noise,
                "measurement_noise": self.measurement_noise,
            },
        )

    def generate_signals(self, bars: Sequence[MarketBar]) -> tuple[PositionSignal, ...]:
        validate_strategy_bars(bars)
        level = log(bars[0].close)
        variance = 1.0
        residuals: list[float] = []
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            observation = log(bar.close)
            predicted_variance = variance + self.process_noise
            innovation = observation - level
            gain = predicted_variance / (predicted_variance + self.measurement_noise)
            level += gain * innovation
            variance = (1.0 - gain) * predicted_variance
            residuals.append(innovation)

            if len(residuals) > self.residual_window:
                residuals.pop(0)

            if index + 1 < self.warmup or len(residuals) < self.residual_window:
                signals.append(PositionSignal.FLAT)
                continue

            center = sum(residuals) / len(residuals)
            scale = sqrt(sum((value - center) ** 2 for value in residuals) / len(residuals))
            z_score = (innovation - center) / max(scale, 1e-12)

            if z_score > self.entry_z:
                position = PositionSignal.SHORT
            elif z_score < -self.entry_z:
                position = PositionSignal.LONG
            elif abs(z_score) <= self.exit_z:
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


class VolatilityBreakout:
    """Price-channel breakout whose width adapts to trailing realized volatility."""

    def __init__(
        self,
        *,
        window: int = 40,
        volatility_window: int = 20,
        entry_multiplier: float = 1.25,
        exit_multiplier: float = 0.25,
    ) -> None:
        if window < 10 or volatility_window < 5:
            raise ValueError("Volatility breakout windows are too short.")
        if entry_multiplier <= 0:
            raise ValueError("Volatility breakout entry multiplier must be positive.")
        if exit_multiplier < 0 or exit_multiplier >= entry_multiplier:
            raise ValueError("Volatility breakout exit multiplier is invalid.")
        self.window = window
        self.volatility_window = volatility_window
        self.entry_multiplier = entry_multiplier
        self.exit_multiplier = exit_multiplier

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="volatility_breakout",
            family=StrategyFamily.VOLATILITY,
            parameters={
                "window": self.window,
                "volatility_window": self.volatility_window,
                "entry_multiplier": self.entry_multiplier,
                "exit_multiplier": self.exit_multiplier,
            },
        )

    def generate_signals(self, bars: Sequence[MarketBar]) -> tuple[PositionSignal, ...]:
        validate_strategy_bars(bars)
        prices = [log(bar.close) for bar in bars]
        warmup = max(self.window, self.volatility_window)
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for index in range(len(bars)):
            if index < warmup:
                signals.append(PositionSignal.FLAT)
                continue

            returns = [
                prices[position_index] - prices[position_index - 1]
                for position_index in range(
                    index - self.volatility_window + 1,
                    index + 1,
                )
            ]
            volatility = sqrt(sum(value * value for value in returns) / len(returns))
            prior = prices[index - self.window : index]
            center = sum(prior) / len(prior)
            displacement = prices[index] - center
            entry = self.entry_multiplier * volatility * sqrt(self.window)
            exit_value = self.exit_multiplier * volatility * sqrt(self.window)

            if displacement > entry:
                position = PositionSignal.LONG
            elif displacement < -entry:
                position = PositionSignal.SHORT
            elif abs(displacement) <= exit_value:
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


class CointegrationDiagnostics(BaseModel):
    """Dependency-light Engle–Granger diagnostics for two aligned price series."""

    model_config = ConfigDict(frozen=True)

    observations: int = Field(ge=3)
    intercept: float
    hedge_ratio: float
    residual_autocorrelation: float
    half_life_bars: float | None
    latest_z_score: float
    mean_reversion_supported: bool


def analyze_cointegration_pair(
    left_prices: Sequence[float],
    right_prices: Sequence[float],
) -> CointegrationDiagnostics:
    """Fit an OLS hedge ratio and causal residual mean-reversion diagnostics."""

    if len(left_prices) != len(right_prices) or len(left_prices) < 30:
        raise ValueError("Cointegration diagnostics require equal series of at least 30 rows.")
    if any(value <= 0 for value in (*left_prices, *right_prices)):
        raise ValueError("Cointegration price inputs must be positive.")
    left = [log(value) for value in left_prices]
    right = [log(value) for value in right_prices]
    right_mean = sum(right) / len(right)
    left_mean = sum(left) / len(left)
    variance = sum((value - right_mean) ** 2 for value in right)
    hedge_ratio = (
        sum((x - right_mean) * (y - left_mean) for x, y in zip(right, left, strict=True)) / variance
        if variance > 0
        else 0.0
    )
    intercept = left_mean - hedge_ratio * right_mean
    residuals = [y - intercept - hedge_ratio * x for x, y in zip(right, left, strict=True)]
    autocorrelation = _autocorrelation(residuals)
    half_life = -log(2.0) / log(abs(autocorrelation)) if 0 < abs(autocorrelation) < 1 else None
    residual_mean = sum(residuals) / len(residuals)
    residual_scale = sqrt(sum((value - residual_mean) ** 2 for value in residuals) / len(residuals))
    latest_z = (residuals[-1] - residual_mean) / max(residual_scale, 1e-12)

    return CointegrationDiagnostics(
        observations=len(residuals),
        intercept=intercept,
        hedge_ratio=hedge_ratio,
        residual_autocorrelation=autocorrelation,
        half_life_bars=half_life,
        latest_z_score=latest_z,
        mean_reversion_supported=(-0.05 <= autocorrelation < 0.98 and half_life is not None),
    )


class RiskParityAllocation(BaseModel):
    """Research-only inverse-volatility risk budget across independent assets."""

    model_config = ConfigDict(frozen=True)

    weights: dict[str, float]
    volatility_estimates: dict[str, float]
    fully_invested: bool
    live_trading_authorized: Literal[False] = False


def inverse_volatility_risk_parity(
    returns_by_asset: Mapping[str, Sequence[float]],
) -> RiskParityAllocation:
    """Allocate normalized inverse volatility without sending any order."""

    if len(returns_by_asset) < 2:
        raise ValueError("Risk parity requires at least two assets.")
    volatilities: dict[str, float] = {}

    for asset, values in returns_by_asset.items():
        if len(values) < 3:
            raise ValueError(f"Risk parity asset '{asset}' has insufficient returns.")
        center = sum(values) / len(values)
        volatility = sqrt(sum((value - center) ** 2 for value in values) / len(values))
        volatilities[asset] = max(volatility, 1e-12)

    inverse = {asset: 1.0 / value for asset, value in volatilities.items()}
    total = sum(inverse.values())
    weights = {asset: value / total for asset, value in inverse.items()}

    return RiskParityAllocation(
        weights=weights,
        volatility_estimates=volatilities,
        fully_invested=abs(sum(weights.values()) - 1.0) < 1e-9,
    )


def _autocorrelation(values: Sequence[float]) -> float:
    left = values[:-1]
    right = values[1:]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )

    return numerator / denominator if denominator > 0 else 0.0
