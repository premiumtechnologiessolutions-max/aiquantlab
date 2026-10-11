from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from math import sqrt

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies.base import (
    PositionSignal,
    StrategyDescriptor,
    StrategyFamily,
    validate_strategy_bars,
)


class MovingAverageCrossover:
    """Long/short trend strategy based on two rolling close averages."""

    def __init__(
        self,
        *,
        fast_window: int = 20,
        slow_window: int = 50,
    ) -> None:
        if fast_window < 2:
            raise ValueError("Fast window must be at least two bars.")

        if slow_window <= fast_window:
            raise ValueError("Slow window must be greater than fast window.")

        self.fast_window = fast_window
        self.slow_window = slow_window

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible strategy configuration."""

        return StrategyDescriptor(
            name="moving_average_crossover",
            family=StrategyFamily.TREND,
            parameters={
                "fast_window": self.fast_window,
                "slow_window": self.slow_window,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate causal signals using closes available at each bar."""

        validate_strategy_bars(bars)

        closes = deque[float]()
        rolling_sum = 0.0
        signals: list[PositionSignal] = []

        for bar in bars:
            closes.append(bar.close)
            rolling_sum += bar.close

            if len(closes) > self.slow_window:
                rolling_sum -= closes.popleft()

            if len(closes) < self.slow_window:
                signals.append(PositionSignal.FLAT)
                continue

            slow_average = rolling_sum / self.slow_window
            fast_average = sum(list(closes)[-self.fast_window :]) / self.fast_window

            if fast_average > slow_average:
                signals.append(PositionSignal.LONG)
            elif fast_average < slow_average:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class ZScoreMeanReversion:
    """Contrarian strategy that trades statistically unusual closes."""

    def __init__(
        self,
        *,
        window: int = 30,
        entry_z: float = 1.5,
        exit_z: float = 0.25,
    ) -> None:
        if window < 3:
            raise ValueError("Mean-reversion window must be at least three bars.")

        if entry_z <= 0:
            raise ValueError("Entry z-score must be greater than zero.")

        if exit_z < 0 or exit_z >= entry_z:
            raise ValueError("Exit z-score must be non-negative and below entry z-score.")

        self.window = window
        self.entry_z = entry_z
        self.exit_z = exit_z

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible strategy configuration."""

        return StrategyDescriptor(
            name="zscore_mean_reversion",
            family=StrategyFamily.MEAN_REVERSION,
            parameters={
                "window": self.window,
                "entry_z": self.entry_z,
                "exit_z": self.exit_z,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate causal z-score signals with a small exit band."""

        validate_strategy_bars(bars)

        closes = deque[float]()
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for bar in bars:
            closes.append(bar.close)

            if len(closes) > self.window:
                closes.popleft()

            if len(closes) < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            mean = sum(closes) / self.window
            variance = sum((value - mean) ** 2 for value in closes) / self.window
            standard_deviation = sqrt(variance)
            z_score = (
                (bar.close - mean) / standard_deviation
                if standard_deviation > 0
                else 0.0
            )

            if z_score >= self.entry_z:
                position = PositionSignal.SHORT
            elif z_score <= -self.entry_z:
                position = PositionSignal.LONG
            elif abs(z_score) <= self.exit_z:
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


class BuyAndHold:
    """Simple long-only baseline used to contextualize research results."""

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible baseline description."""

        return StrategyDescriptor(
            name="buy_and_hold",
            family=StrategyFamily.BASELINE,
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Request a long position from the first observable bar onward."""

        validate_strategy_bars(bars)

        return tuple(PositionSignal.LONG for _ in bars)


class ExponentialMovingAverageCrossover:
    """Trend strategy using fast and slow exponentially weighted averages."""

    def __init__(self, *, fast_window: int = 12, slow_window: int = 26) -> None:
        if fast_window < 2:
            raise ValueError("Fast EMA window must be at least two bars.")

        if slow_window <= fast_window:
            raise ValueError("Slow EMA window must be greater than fast EMA window.")

        self.fast_window = fast_window
        self.slow_window = slow_window

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible EMA strategy configuration."""

        return StrategyDescriptor(
            name="ema_crossover",
            family=StrategyFamily.TREND,
            parameters={
                "fast_window": self.fast_window,
                "slow_window": self.slow_window,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate causal EMA cross signals from observed closes."""

        validate_strategy_bars(bars)
        fast_alpha = 2.0 / (self.fast_window + 1.0)
        slow_alpha = 2.0 / (self.slow_window + 1.0)
        fast_ema = bars[0].close
        slow_ema = bars[0].close
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            if index > 0:
                fast_ema = fast_alpha * bar.close + (1.0 - fast_alpha) * fast_ema
                slow_ema = slow_alpha * bar.close + (1.0 - slow_alpha) * slow_ema

            if index + 1 < self.slow_window:
                signals.append(PositionSignal.FLAT)
            elif fast_ema > slow_ema:
                signals.append(PositionSignal.LONG)
            elif fast_ema < slow_ema:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class RelativeStrengthIndexReversion:
    """Mean-reversion strategy driven by a rolling relative-strength index."""

    def __init__(
        self,
        *,
        window: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        exit_level: float = 50.0,
    ) -> None:
        if window < 2:
            raise ValueError("RSI window must be at least two bars.")

        if not 0 < oversold < exit_level < overbought < 100:
            raise ValueError(
                "RSI levels must satisfy 0 < oversold < exit < overbought < 100."
            )

        self.window = window
        self.oversold = oversold
        self.overbought = overbought
        self.exit_level = exit_level

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible RSI strategy configuration."""

        return StrategyDescriptor(
            name="rsi_mean_reversion",
            family=StrategyFamily.MEAN_REVERSION,
            parameters={
                "window": self.window,
                "oversold": self.oversold,
                "overbought": self.overbought,
                "exit_level": self.exit_level,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate causal RSI entries with a neutral exit threshold."""

        validate_strategy_bars(bars)
        changes: deque[float] = deque()
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = [PositionSignal.FLAT]

        for index in range(1, len(bars)):
            changes.append(bars[index].close - bars[index - 1].close)

            if len(changes) > self.window:
                changes.popleft()

            if len(changes) < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            gains = sum(max(change, 0.0) for change in changes) / self.window
            losses = sum(max(-change, 0.0) for change in changes) / self.window

            if losses == 0:
                rsi = 100.0 if gains > 0 else 50.0
            else:
                relative_strength = gains / losses
                rsi = 100.0 - 100.0 / (1.0 + relative_strength)

            if rsi <= self.oversold:
                position = PositionSignal.LONG
            elif rsi >= self.overbought:
                position = PositionSignal.SHORT
            elif (
                position is PositionSignal.LONG and rsi >= self.exit_level
            ) or (
                position is PositionSignal.SHORT and rsi <= self.exit_level
            ):
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


class DonchianBreakout:
    """Breakout strategy comparing the close with the prior price channel."""

    def __init__(self, *, window: int = 20) -> None:
        if window < 2:
            raise ValueError("Donchian window must be at least two bars.")

        self.window = window

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible Donchian strategy configuration."""

        return StrategyDescriptor(
            name="donchian_breakout",
            family=StrategyFamily.BREAKOUT,
            parameters={"window": self.window},
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Use only prior completed bars to form each breakout channel."""

        validate_strategy_bars(bars)
        prior_bars: deque[MarketBar] = deque()
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for bar in bars:
            if len(prior_bars) < self.window:
                signals.append(PositionSignal.FLAT)
            else:
                upper = max(item.high for item in prior_bars)
                lower = min(item.low for item in prior_bars)
                midpoint = (upper + lower) / 2.0

                if bar.close > upper:
                    position = PositionSignal.LONG
                elif bar.close < lower:
                    position = PositionSignal.SHORT
                elif (
                    position is PositionSignal.LONG and bar.close < midpoint
                ) or (
                    position is PositionSignal.SHORT and bar.close > midpoint
                ):
                    position = PositionSignal.FLAT

                signals.append(position)

            prior_bars.append(bar)

            if len(prior_bars) > self.window:
                prior_bars.popleft()

        return tuple(signals)


class BollingerBandReversion:
    """Volatility-aware mean-reversion strategy using rolling bands."""

    def __init__(self, *, window: int = 20, standard_deviations: float = 2.0) -> None:
        if window < 3:
            raise ValueError("Bollinger window must be at least three bars.")

        if standard_deviations <= 0:
            raise ValueError("Bollinger deviation multiplier must be positive.")

        self.window = window
        self.standard_deviations = standard_deviations

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible Bollinger strategy configuration."""

        return StrategyDescriptor(
            name="bollinger_reversion",
            family=StrategyFamily.VOLATILITY,
            parameters={
                "window": self.window,
                "standard_deviations": self.standard_deviations,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate band entries and mean exits without future information."""

        validate_strategy_bars(bars)
        closes: deque[float] = deque()
        position = PositionSignal.FLAT
        signals: list[PositionSignal] = []

        for bar in bars:
            closes.append(bar.close)

            if len(closes) > self.window:
                closes.popleft()

            if len(closes) < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            mean = sum(closes) / self.window
            variance = sum((value - mean) ** 2 for value in closes) / self.window
            deviation = sqrt(variance)
            upper = mean + self.standard_deviations * deviation
            lower = mean - self.standard_deviations * deviation

            if bar.close >= upper and deviation > 0:
                position = PositionSignal.SHORT
            elif bar.close <= lower and deviation > 0:
                position = PositionSignal.LONG
            elif (
                position is PositionSignal.LONG and bar.close >= mean
            ) or (
                position is PositionSignal.SHORT and bar.close <= mean
            ):
                position = PositionSignal.FLAT

            signals.append(position)

        return tuple(signals)


class MovingAverageConvergenceDivergence:
    """Momentum strategy using the MACD line and its signal average."""

    def __init__(
        self,
        *,
        fast_window: int = 12,
        slow_window: int = 26,
        signal_window: int = 9,
    ) -> None:
        if fast_window < 2 or signal_window < 2:
            raise ValueError("MACD fast and signal windows must be at least two bars.")

        if slow_window <= fast_window:
            raise ValueError("MACD slow window must be greater than its fast window.")

        self.fast_window = fast_window
        self.slow_window = slow_window
        self.signal_window = signal_window

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible MACD strategy configuration."""

        return StrategyDescriptor(
            name="macd_momentum",
            family=StrategyFamily.MOMENTUM,
            parameters={
                "fast_window": self.fast_window,
                "slow_window": self.slow_window,
                "signal_window": self.signal_window,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate causal MACD momentum signals."""

        validate_strategy_bars(bars)
        fast_alpha = 2.0 / (self.fast_window + 1.0)
        slow_alpha = 2.0 / (self.slow_window + 1.0)
        signal_alpha = 2.0 / (self.signal_window + 1.0)
        fast_ema = bars[0].close
        slow_ema = bars[0].close
        signal_ema = 0.0
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            if index > 0:
                fast_ema = fast_alpha * bar.close + (1.0 - fast_alpha) * fast_ema
                slow_ema = slow_alpha * bar.close + (1.0 - slow_alpha) * slow_ema

            macd = fast_ema - slow_ema
            signal_ema = (
                macd
                if index == 0
                else signal_alpha * macd + (1.0 - signal_alpha) * signal_ema
            )
            warmup = self.slow_window + self.signal_window - 1

            if index + 1 < warmup:
                signals.append(PositionSignal.FLAT)
            elif macd > signal_ema:
                signals.append(PositionSignal.LONG)
            elif macd < signal_ema:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)


class RateOfChangeMomentum:
    """Momentum strategy based on the causal rate of change of closing prices."""

    def __init__(self, *, window: int = 12, threshold_percent: float = 0.1) -> None:
        if window < 2:
            raise ValueError("Rate-of-change window must be at least two bars.")

        if threshold_percent < 0:
            raise ValueError("Rate-of-change threshold cannot be negative.")

        self.window = window
        self.threshold_percent = threshold_percent

    @property
    def descriptor(self) -> StrategyDescriptor:
        """Return the reproducible rate-of-change strategy configuration."""

        return StrategyDescriptor(
            name="roc_momentum",
            family=StrategyFamily.MOMENTUM,
            parameters={
                "window": self.window,
                "threshold_percent": self.threshold_percent,
            },
        )

    def generate_signals(
        self,
        bars: Sequence[MarketBar],
    ) -> tuple[PositionSignal, ...]:
        """Generate signals from a close observed exactly ``window`` bars ago."""

        validate_strategy_bars(bars)
        signals: list[PositionSignal] = []

        for index, bar in enumerate(bars):
            if index < self.window:
                signals.append(PositionSignal.FLAT)
                continue

            reference = bars[index - self.window].close
            rate = (bar.close / reference - 1.0) * 100.0

            if rate > self.threshold_percent:
                signals.append(PositionSignal.LONG)
            elif rate < -self.threshold_percent:
                signals.append(PositionSignal.SHORT)
            else:
                signals.append(PositionSignal.FLAT)

        return tuple(signals)
