from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies import (
    STRATEGY_CATALOG,
    SUPPORTED_STRATEGIES,
    PositionSignal,
    StrategyFamily,
    build_strategy,
    neighboring_variants,
)


def make_market_bars(count: int = 180) -> tuple[MarketBar, ...]:
    """Build a trending and oscillating series that exercises every family."""

    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[MarketBar] = []

    for index in range(count):
        cycle = ((index % 24) - 12) * 0.00008
        close = 1.1000 + index * 0.00004 + cycle
        open_price = close - 0.00003
        bars.append(
            MarketBar(
                pair="EURUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * index),
                open=open_price,
                high=max(open_price, close) + 0.0002,
                low=min(open_price, close) - 0.0002,
                close=close,
                tick_volume=1_000 + index,
                spread_points=8,
            )
        )

    return tuple(bars)


def test_catalog_contains_multiple_strategy_families() -> None:
    assert len(SUPPORTED_STRATEGIES) == 16
    assert len(STRATEGY_CATALOG) == len(SUPPORTED_STRATEGIES)
    assert {specification.family for specification in STRATEGY_CATALOG} >= {
        StrategyFamily.TREND,
        StrategyFamily.MOMENTUM,
        StrategyFamily.BREAKOUT,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.VOLATILITY,
        StrategyFamily.ADAPTIVE,
        StrategyFamily.STATISTICAL,
        StrategyFamily.BASELINE,
    }
    assert sum(specification.research_tier == "advanced" for specification in STRATEGY_CATALOG) == 7


def test_every_catalog_strategy_is_causal_on_each_prefix() -> None:
    bars = make_market_bars()

    for name in SUPPORTED_STRATEGIES:
        strategy = build_strategy(name)
        complete = strategy.generate_signals(bars)

        assert len(complete) == len(bars)
        assert set(complete) <= {
            PositionSignal.SHORT,
            PositionSignal.FLAT,
            PositionSignal.LONG,
        }

        for prefix_length in (1, 20, 60, len(bars)):
            prefix = bars[:prefix_length]
            prefix_signals = build_strategy(name).generate_signals(prefix)

            assert prefix_signals == complete[:prefix_length]


def test_every_parameterized_strategy_has_declared_neighboring_variants() -> None:
    for name in SUPPORTED_STRATEGIES:
        strategy = build_strategy(name)
        variants = neighboring_variants(name, strategy.descriptor.parameters)

        assert variants
        assert variants[0].descriptor == strategy.descriptor
        assert all(variant.descriptor.name == name for variant in variants)


def test_advanced_strategies_emit_non_flat_decisions_on_structured_series() -> None:
    bars = make_market_bars(240)
    advanced_names = (
        "kalman_adaptive_trend",
        "multi_horizon_vol_trend",
        "variance_ratio_regime_switch",
        "garman_klass_vol_breakout",
        "time_series_momentum",
        "kalman_mean_reversion",
        "volatility_breakout",
    )

    for name in advanced_names:
        signals = build_strategy(name).generate_signals(bars)

        assert any(signal is not PositionSignal.FLAT for signal in signals)
