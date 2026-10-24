"""Gold/forex instrument-boundary tests: paper/research only."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_quant_lab.backtesting import BacktestConfig, run_backtest
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.simulation import (
    MarketQuote, SimulationLedger, SimulationMode, SimulationPolicy, SimulationStatus,
)
from ai_quant_lab.strategies import BuyAndHold, PositionSignal


def _gold_bars() -> list[MarketBar]:
    start = datetime(2026, 10, 1, tzinfo=UTC)
    prices = [3000.0, 3000.0, 3010.0]
    return [
        MarketBar(
            pair="XAUUSD",
            timeframe="M15",
            timestamp=start + timedelta(minutes=15 * i),
            open=price,
            high=price + 1,
            low=price - 1,
            close=price,
            tick_volume=10,
            spread_points=30,  # $0.30 per ounce at 0.01 per point
        )
        for i, price in enumerate(prices)
    ]


def test_gold_market_bar_accepts_quote_currency_usd_prices() -> None:
    bars = _gold_bars()
    assert bars[0].pair == "XAUUSD"
    assert bars[-1].close == 3010.0


def test_gold_cannot_inherit_forex_quantity_and_point_defaults() -> None:
    bars = _gold_bars()
    with pytest.raises(ValueError, match="explicit BacktestConfig"):
        run_backtest(bars, BuyAndHold())
    with pytest.raises(ValueError, match="explicit BacktestConfig"):
        run_backtest(bars, BuyAndHold(), BacktestConfig(point_size=0.01))
    with pytest.raises(ValueError, match="explicit BacktestConfig"):
        run_backtest(bars, BuyAndHold(), BacktestConfig(quantity=2))


def test_gold_backtest_costs_are_dollars_per_ounce_times_ounces() -> None:
    bars = _gold_bars()
    result = run_backtest(
        bars,
        BuyAndHold(),
        BacktestConfig(
            initial_capital=10000,
            quantity=2,  # troy ounces (not 2 broker lots)
            point_size=0.01,
            slippage_points=5,
            commission_per_side=0.20,
        ),
    )
    assert result.metrics.trade_count == 1
    trade = result.trades[0]
    assert trade.entry_time == bars[1].timestamp
    assert trade.gross_profit == pytest.approx(20.0)
    # Each side: 2oz * ($0.15 half-spread + $0.05 slip) + $0.20 = $0.60.
    assert trade.costs == pytest.approx(1.20)
    assert trade.net_profit == pytest.approx(18.80)


def test_gold_simulation_requires_explicit_price_increment(tmp_path) -> None:
    ledger = SimulationLedger(tmp_path / "gold.sqlite3")
    now = datetime.now(UTC)
    quote = MarketQuote(timestamp=now, bid=3000.00, ask=3000.50)

    with pytest.raises(ValueError, match="explicit SimulationPolicy"):
        ledger.submit(
            mode=SimulationMode.PAPER, pair="XAUUSD", timeframe="M15",
            strategy_version_id="gold-shadow", signal=PositionSignal.LONG,
            requested_units=1, quote=quote, observed_at=now,
        )

    decision = ledger.submit(
        mode=SimulationMode.PAPER, pair="XAUUSD", timeframe="M15",
        strategy_version_id="gold-shadow", signal=PositionSignal.LONG,
        requested_units=1, quote=quote, observed_at=now,
        policy=SimulationPolicy(
            point_size=0.01, maximum_spread_points=100, slippage_points=2,
        ),
    )
    assert decision.status is SimulationStatus.FILLED
    assert decision.spread_points == pytest.approx(50)
    assert decision.simulated_fill_price == pytest.approx(3000.52)


def test_fx_legacy_defaults_remain_valid() -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    bars = [
        MarketBar(
            pair="EURUSD", timeframe="M15",
            timestamp=now + timedelta(minutes=15*i),
            open=1.10 + .0001*i, high=1.101 + .0001*i,
            low=1.099 + .0001*i, close=1.10 + .0001*i,
            tick_volume=10, spread_points=2,
        )
        for i in range(3)
    ]
    result = run_backtest(bars, BuyAndHold())
    assert result.metrics.trade_count == 1
    assert result.trades[0].costs > 0
