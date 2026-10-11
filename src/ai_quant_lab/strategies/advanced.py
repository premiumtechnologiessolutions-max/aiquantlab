from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from math import log, sqrt

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies.base import (
    PositionSignal,
    StrategyDescriptor,
    StrategyFamily,
    validate_strategy_bars,
)


class KalmanAdaptiveTrend:
    """State-space trend estimator with volatility-normalized slope decisions."""

    def __init__(
        self,
        *,
        warmup: int = 32,
        volatility_window: int = 32,
        process_noise: float = 1e-8,
        measurement_noise: float = 1e-5,
        signal_threshold: float = 0.15,
    ) -> None:
        if warmup < 5:
            raise ValueError("Kalman warmup must contain at least five bars.")

        if volatility_window < 3:
            raise ValueError("Kalman volatility window must contain at least three bars.")

        if process_noise <= 0 or measurement_noise <= 0:
            raise ValueError("Kalman noise variances must be positive.")

        if signal_threshold <= 0:
            raise ValueError("Kalman signal threshold must be positive.")

        self.warmup = warmup
        self.volatility_window = volatility_window
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.signal_threshold = signal_threshold

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="kalman_adaptive_trend",
            family=StrategyFamily.ADAPTIVE,
            parameters={
                "warmup": self.warmup,
                "volatility_window": self.volatility_window,
                "process_noise": self.process_noise,
                "measurement_noise": self.measurement_noise,
                "signal_threshold": self.signal_threshold,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Estimate latent log-price level and slope using observations seen so far."""

        validate_strategy_bars(bars)
        level = log(bars[0].close)
        slope = 0.0
        p00 = 1.0
        p01 = 0.0
        p10 = 0.0
        p11 = 1.0
        previous_log_close = level
        returns: deque[float] = deque()
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            observed = log(bar.close)

            if index > 0:
                returns.append(observed - previous_log_close)

                if len(returns) > self.volatility_window:
                    returns.popleft()

            predicted_level = level + slope
            predicted_slope = slope
            predicted_p00 = p00 + p01 + p10 + p11 + self.process_noise
            predicted_p01 = p01 + p11
            predicted_p10 = p10 + p11
            predicted_p11 = p11 + self.process_noise
            innovation_variance = predicted_p00 + self.measurement_noise
            level_gain = predicted_p00 / innovation_variance
            slope_gain = predicted_p10 / innovation_variance
            innovation = observed - predicted_level
            level = predicted_level + level_gain * innovation
            slope = predicted_slope + slope_gain * innovation
            p00 = (1.0 - level_gain) * predicted_p00
            p01 = (1.0 - level_gain) * predicted_p01
            p10 = predicted_p10 - slope_gain * predicted_p00
            p11 = predicted_p11 - slope_gain * predicted_p01
            previous_log_close = observed

            if index + 1 < self.warmup or len(returns) < self.volatility_window:
                signals.append(PositionSignal.FLAT)
                continue

            realized_volatility = sqrt(sum(value * value for value in returns) / len(returns))
            normalized_slope = slope / max(realized_volatility, 1e-12)

            if normalized_slope > self.signal_threshold:
                signals.append(PositionSignal.LONG)
            elif normalized_slope < -self.signal_threshold:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class MultiHorizonVolatilityTrend:
    """Blend several trend horizons after scaling each by realized volatility."""

    def __init__(
        self,
        *,
        short_horizon: int = 8,
        medium_horizon: int = 32,
        long_horizon: int = 96,
        volatility_window: int = 32,
        signal_threshold: float = 0.75,
    ) -> None:
        if not 2 <= short_horizon < medium_horizon < long_horizon:
            raise ValueError("Trend horizons must satisfy 2 <= short < medium < long.")

        if volatility_window < 3:
            raise ValueError("Trend volatility window must contain at least three bars.")

        if signal_threshold <= 0:
            raise ValueError("Trend signal threshold must be positive.")

        self.short_horizon = short_horizon
        self.medium_horizon = medium_horizon
        self.long_horizon = long_horizon
        self.volatility_window = volatility_window
        self.signal_threshold = signal_threshold

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="multi_horizon_vol_trend",
            family=StrategyFamily.ADAPTIVE,
            parameters={
                "short_horizon": self.short_horizon,
                "medium_horizon": self.medium_horizon,
                "long_horizon": self.long_horizon,
                "volatility_window": self.volatility_window,
                "signal_threshold": self.signal_threshold,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Use volatility-scaled log returns from three causal horizons."""

        validate_strategy_bars(bars)
        log_closes = [log(bar.close) for bar in bars]
        signals: list[PositionSignal] = []
        warmup = max(self.long_horizon, self.volatility_window)
        horizons = (self.short_horizon, self.medium_horizon, self.long_horizon)

        for index in range(len(bars)):
            if index < warmup:
                signals.append(PositionSignal.FLAT)
                continue

            recent_returns = [
                log_closes[position] - log_closes[position - 1]
                for position in range(index - self.volatility_window + 1, index + 1)
            ]
            realized_volatility = sqrt(
                sum(value * value for value in recent_returns) / len(recent_returns)
            )
            denominator = max(realized_volatility, 1e-12)
            horizon_scores = [
                (log_closes[index] - log_closes[index - horizon]) / (denominator * sqrt(horizon))
                for horizon in horizons
            ]
            combined_score = sum(horizon_scores) / len(horizon_scores)

            if combined_score > self.signal_threshold:
                signals.append(PositionSignal.LONG)
            elif combined_score < -self.signal_threshold:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class VarianceRatioRegimeSwitch:
    """Switch between trend and reversion using a rolling variance-ratio statistic."""

    def __init__(
        self,
        *,
        window: int = 80,
        aggregation_lag: int = 4,
        regime_threshold: float = 0.08,
        zscore_window: int = 20,
        entry_z: float = 1.25,
    ) -> None:
        if window < 20:
            raise ValueError("Variance-ratio window must contain at least twenty bars.")

        if aggregation_lag < 2 or aggregation_lag >= window:
            raise ValueError("Variance-ratio aggregation lag must be between two and window-1.")

        if regime_threshold <= 0:
            raise ValueError("Variance-ratio regime threshold must be positive.")

        if zscore_window < 3 or zscore_window >= window:
            raise ValueError("Variance-ratio z-score window must be between three and window-1.")

        if entry_z <= 0:
            raise ValueError("Variance-ratio z-score entry must be positive.")

        self.window = window
        self.aggregation_lag = aggregation_lag
        self.regime_threshold = regime_threshold
        self.zscore_window = zscore_window
        self.entry_z = entry_z

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="variance_ratio_regime_switch",
            family=StrategyFamily.STATISTICAL,
            parameters={
                "window": self.window,
                "aggregation_lag": self.aggregation_lag,
                "regime_threshold": self.regime_threshold,
                "zscore_window": self.zscore_window,
                "entry_z": self.entry_z,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Estimate persistence, then apply the compatible causal signal family."""

        validate_strategy_bars(bars)
        closes = [bar.close for bar in bars]
        log_closes = [log(value) for value in closes]
        signals: list[PositionSignal] = []

        for index in range(len(bars)):
            if index < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            one_step = [
                log_closes[position] - log_closes[position - 1]
                for position in range(index - self.window + 1, index + 1)
            ]
            aggregated = [
                sum(one_step[start : start + self.aggregation_lag])
                for start in range(len(one_step) - self.aggregation_lag + 1)
            ]
            one_variance = _variance(one_step)
            ratio = (
                _variance(aggregated) / (self.aggregation_lag * one_variance)
                if one_variance > 0
                else 1.0
            )

            if ratio > 1.0 + self.regime_threshold:
                window_return = log_closes[index] - log_closes[index - self.window]
                signals.append(_direction(window_return))
                continue

            if ratio < 1.0 - self.regime_threshold:
                sample = closes[index - self.zscore_window + 1 : index + 1]
                mean = sum(sample) / len(sample)
                deviation = sqrt(_variance(sample))
                zscore = (closes[index] - mean) / deviation if deviation > 0 else 0.0

                if zscore > self.entry_z:
                    signals.append(PositionSignal.SHORT)
                elif zscore < -self.entry_z:
                    signals.append(PositionSignal.LONG)
                else:
                    signals.append(PositionSignal.FLAT)
                continue

            signals.append(PositionSignal.FLAT)

        return tuple(signals)


class GarmanKlassVolatilityBreakout:
    """Detect return shocks relative to a trailing OHLC range-volatility estimate."""

    def __init__(
        self,
        *,
        window: int = 30,
        entry_multiplier: float = 1.5,
        exit_multiplier: float = 0.35,
    ) -> None:
        if window < 5:
            raise ValueError("Garman-Klass window must contain at least five bars.")

        if entry_multiplier <= 0:
            raise ValueError("Garman-Klass entry multiplier must be positive.")

        if exit_multiplier < 0 or exit_multiplier >= entry_multiplier:
            raise ValueError("Garman-Klass exit multiplier must be below entry multiplier.")

        self.window = window
        self.entry_multiplier = entry_multiplier
        self.exit_multiplier = exit_multiplier

    @property
    def descriptor(self) -> StrategyDescriptor:
        return StrategyDescriptor(
            name="garman_klass_vol_breakout",
            family=StrategyFamily.VOLATILITY,
            parameters={
                "window": self.window,
                "entry_multiplier": self.entry_multiplier,
                "exit_multiplier": self.exit_multiplier,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Compare the newest close return with volatility from prior OHLC bars only."""

        validate_strategy_bars(bars)
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            if index < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            prior = bars[index - self.window : index]
            variances = [
                max(
                    0.0,
                    0.5 * log(item.high / item.low) ** 2
                    - (2.0 * log(2.0) - 1.0) * log(item.close / item.open) ** 2,
                )
                for item in prior
            ]
            volatility = sqrt(sum(variances) / len(variances))
            close_return = log(bar.close / bars[index - 1].close)

            if close_return > self.entry_multiplier * volatility:
                position = PositionSignal.LONG
            elif close_return < -self.entry_multiplier * volatility:
                position = PositionSignal.SHORT
            elif abs(close_return) <= self.exit_multiplier * volatility:
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0

    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _direction(value: float) -> PositionSignal:
    if value > 0:
        return PositionSignal.LONG

    if value < 0:
        return PositionSignal.SHORT

    return PositionSignal.FLAT
