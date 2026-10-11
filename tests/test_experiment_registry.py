from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.backtesting import BacktestResult, run_backtest
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.experiments import (
    ExperimentRecord,
    ExperimentRegistry,
    StrategyLifecycle,
)
from ai_quant_lab.regimes import MarketRegime
from ai_quant_lab.strategies import (
    BuyAndHold,
)
from ai_quant_lab.strategies.allocation import StrategyCandidateScore, allocate_strategies
from ai_quant_lab.validation import ValidationPolicy, ValidationReport, validate_backtest


def make_result() -> tuple[BacktestResult, ValidationReport]:
    """Create one deterministic strategy result and validation report."""

    start = datetime(2026, 8, 3, tzinfo=UTC)
    bars = [
        MarketBar(
            pair="EURUSD",
            timeframe="M15",
            timestamp=start + timedelta(minutes=15 * index),
            open=1.10 + index * 0.001,
            high=1.102 + index * 0.001,
            low=1.099 + index * 0.001,
            close=1.101 + index * 0.001,
            tick_volume=100,
            spread_points=1,
        )
        for index in range(12)
    ]
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

    return result, validation


def test_registry_preserves_versions_failures_and_experiments(
    tmp_path: Path,
) -> None:
    result, validation = make_result()
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    version = registry.register_strategy(
        descriptor=BuyAndHold().descriptor,
        code_commit="abc123",
    )
    duplicate = registry.register_strategy(
        descriptor=BuyAndHold().descriptor,
        code_commit="abc123",
    )

    assert duplicate == version

    candidate = registry.transition_strategy(
        version.version_id,
        new_status=StrategyLifecycle.CANDIDATE,
        reason="Basic research gates passed.",
    )
    challenger = registry.transition_strategy(
        candidate.version_id,
        new_status=StrategyLifecycle.CHALLENGER,
        reason="Independent validation passed.",
    )
    shadow = registry.transition_strategy(
        challenger.version_id,
        new_status=StrategyLifecycle.SHADOW,
        reason="Approved for simulated shadow observation.",
    )

    with pytest.raises(PermissionError, match="human approval"):
        registry.transition_strategy(
            shadow.version_id,
            new_status=StrategyLifecycle.PAPER,
            reason="Requested paper trial.",
        )

    paper = registry.transition_strategy(
        shadow.version_id,
        new_status=StrategyLifecycle.PAPER,
        reason="Human approved a simulated paper trial.",
        human_approved=True,
    )
    record = ExperimentRecord(
        experiment_id="experiment_000001",
        strategy_version_id=paper.version_id,
        pair="EURUSD",
        timeframe="M15",
        dataset_sha256="a" * 64,
        metrics=result.metrics,
        validation=validation,
        json_report_path="report.json",
        markdown_report_path="report.md",
    )
    registry.record_experiment(record)

    assert registry.get_strategy(version.version_id).status is StrategyLifecycle.PAPER
    assert registry.list_experiments() == (record,)

    with pytest.raises(ValueError, match="already exists"):
        registry.record_experiment(record)


def test_allocator_ranks_only_validated_regime_evidence() -> None:
    result, _ = make_result()
    metrics = result.metrics
    allocation = allocate_strategies(
        pair="EURUSD",
        timeframe="M15",
        regime=MarketRegime.TRENDING_UP,
        candidates=(
            StrategyCandidateScore(
                strategy_version_id="strategy_valid",
                metrics=metrics,
                compatible_regimes=(MarketRegime.TRENDING_UP,),
                validation_passed=True,
            ),
            StrategyCandidateScore(
                strategy_version_id="strategy_unvalidated",
                metrics=metrics,
                compatible_regimes=(MarketRegime.TRENDING_UP,),
                validation_passed=False,
            ),
        ),
    )

    assert allocation.champion_version_id == "strategy_valid"
    assert allocation.rankings[0].shadow_weight == 1.0
    assert allocation.rankings[1].score == 0.0
    assert allocation.live_trading_authorized is False
