from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.backtesting import BacktestConfig, run_backtest
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.experiments import ExperimentRegistry
from ai_quant_lab.regimes import MarketRegime, detect_market_regimes
from ai_quant_lab.research import run_research_experiment
from ai_quant_lab.risk import RiskLimits, assert_safe_mode, calculate_position_units
from ai_quant_lab.strategies import BuyAndHold, MovingAverageCrossover, PositionSignal
from ai_quant_lab.validation import (
    CheckStatus,
    ValidationPolicy,
    chronological_splits,
    monte_carlo_trade_profits,
    purged_chronological_splits,
    validate_backtest,
)


def make_bars(
    count: int,
    *,
    step: float = 0.0002,
) -> list[MarketBar]:
    """Create deterministic chronological EURUSD bars for MVP tests."""

    start = datetime(2026, 8, 3, tzinfo=UTC)
    bars: list[MarketBar] = []

    for index in range(count):
        open_price = 1.1000 + index * step
        close_price = open_price + step / 2.0
        bars.append(
            MarketBar(
                pair="EURUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * index),
                open=open_price,
                high=max(open_price, close_price) + 0.0001,
                low=min(open_price, close_price) - 0.0001,
                close=close_price,
                tick_volume=1_000 + index,
                spread_points=2,
            )
        )

    return bars


def test_moving_average_strategy_is_causal_and_chronological() -> None:
    bars = make_bars(8)
    strategy = MovingAverageCrossover(
        fast_window=2,
        slow_window=4,
    )

    signals = strategy.generate_signals(bars)

    assert signals[:3] == (
        PositionSignal.FLAT,
        PositionSignal.FLAT,
        PositionSignal.FLAT,
    )
    assert signals[-1] is PositionSignal.LONG

    with pytest.raises(ValueError, match="chronological"):
        strategy.generate_signals(tuple(reversed(bars)))


def test_backtest_uses_next_bar_execution_and_includes_costs() -> None:
    bars = make_bars(6)
    result = run_backtest(
        bars,
        BuyAndHold(),
        BacktestConfig(
            quantity=10_000,
            slippage_points=1,
        ),
    )

    assert result.signal_lag_bars == 1
    assert result.metrics.trade_count == 1
    assert result.trades[0].entry_time == bars[1].timestamp
    assert result.trades[0].gross_profit > result.trades[0].net_profit
    assert result.trades[0].costs > 0


def test_regimes_risk_and_validation_stay_research_only() -> None:
    bars = make_bars(12, step=0.001)
    regimes = detect_market_regimes(
        bars,
        window=4,
        trend_threshold=0.001,
        high_volatility_threshold=1.0,
    )
    result = run_backtest(bars, BuyAndHold())
    validation = validate_backtest(
        result,
        ValidationPolicy(
            minimum_trades=1,
            minimum_profit_factor=0,
            minimum_sharpe_ratio=-100,
            maximum_drawdown_percent=100,
        ),
    )

    assert regimes.latest_regime is MarketRegime.TRENDING_UP
    assert validation.passed_quantitative_gates is True
    assert validation.eligible_for_live_trading is False
    assert any(
        check.name == "paper_trading" and check.status is CheckStatus.NOT_RUN
        for check in validation.checks
    )

    assert_safe_mode("paper")

    with pytest.raises(ValueError, match="live trading"):
        assert_safe_mode("live")

    units = calculate_position_units(
        account_equity=10_000,
        stop_distance_price=0.001,
        limits=RiskLimits(maximum_position_units=50_000),
    )

    assert units == 50_000


def test_walk_forward_and_monte_carlo_are_reproducible() -> None:
    result = run_backtest(make_bars(10), BuyAndHold())

    assert chronological_splits(
        100,
        train_size=50,
        test_size=20,
    ) == (
        (range(50), range(50, 70)),
        (range(70), range(70, 90)),
    )
    assert purged_chronological_splits(
        100,
        train_size=50,
        test_size=20,
        purge_size=2,
    ) == (
        (range(50), range(52, 72)),
        (range(70), range(72, 92)),
    )

    first = monte_carlo_trade_profits(result.trades, simulations=20, seed=11)
    second = monte_carlo_trade_profits(result.trades, simulations=20, seed=11)

    assert first == second


def test_complete_research_pipeline_writes_auditable_reports(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "processed"
    output_root = tmp_path / "experiments"
    store = ParquetMarketStore(data_root)
    store.write_bars(make_bars(80))

    result = run_research_experiment(
        pair="EURUSD",
        timeframe="M15",
        data_root=data_root,
        output_root=output_root,
        strategy_name="buy_and_hold",
        regime_window=10,
        validation_policy=ValidationPolicy(
            minimum_trades=1,
            minimum_profit_factor=0,
            minimum_sharpe_ratio=-100,
            maximum_drawdown_percent=100,
        ),
    )

    assert result.json_report_path.exists()
    assert result.markdown_report_path.exists()
    assert result.intelligence_profile_path.exists()
    assert result.walk_forward is not None
    assert result.walk_forward.windows
    assert result.parameter_stability.variants

    payload = json.loads(result.json_report_path.read_text(encoding="utf-8"))

    assert payload["dataset"]["bar_count"] == 80
    assert payload["strategy_version_id"] == result.strategy_version_id
    assert payload["backtest"]["signal_lag_bars"] == 1
    assert payload["validation"]["eligible_for_live_trading"] is False
    completed_stages = {check["name"]: check["status"] for check in payload["validation"]["checks"]}
    assert completed_stages["walk_forward"] != "not_run"
    assert completed_stages["monte_carlo"] != "not_run"
    assert completed_stages["parameter_stability"] != "not_run"
    assert len(payload["agent_tasks"]) == 6
    assert all(task["status"] == "completed" for task in payload["agent_tasks"])

    registry = ExperimentRegistry(output_root / "registry.sqlite3")

    assert len(registry.list_strategies()) == 1
    assert len(registry.list_experiments()) == 1
