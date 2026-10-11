from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_quant_lab.backtesting import BacktestMetrics
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.experiments import StrategyLifecycle
from ai_quant_lab.intelligence import (
    PairIntelligenceProfile,
    PairIntelligenceStore,
    ProbabilisticForecast,
    StrategyEvidence,
)
from ai_quant_lab.regimes import MarketRegime, detect_change_points


def make_metrics() -> BacktestMetrics:
    """Return controlled evidence for intelligence profile tests."""

    return BacktestMetrics(
        net_profit=100,
        net_return_percent=1,
        maximum_drawdown_percent=2,
        sharpe_ratio=1,
        sortino_ratio=1.5,
        profit_factor=1.2,
        expected_value=10,
        win_rate_percent=60,
        trade_count=10,
    )


def test_forecast_requires_coherent_probabilities() -> None:
    with pytest.raises(ValidationError, match="sum to one"):
        ProbabilisticForecast(
            issued_at=datetime.now(UTC),
            horizon_bars=4,
            probability_up=0.7,
            probability_down=0.4,
            probability_range=0.1,
            expected_return=0.001,
            expected_volatility=0.002,
            regime=MarketRegime.TRENDING_UP,
            confidence=0.6,
            data_quality_score=1.0,
            supporting_reasons=("Trailing trend is positive.",),
            opposing_reasons=("Volatility is elevated.",),
            invalidation_conditions=("Regime changes.",),
            model_version="forecast_1",
        )


def test_pair_intelligence_store_preserves_snapshots(
    tmp_path: Path,
) -> None:
    store = PairIntelligenceStore(tmp_path / "intelligence")
    profile = PairIntelligenceProfile(
        profile_id="profile_000001",
        pair="EURUSD",
        timeframe="M15",
        dataset_sha256="b" * 64,
        latest_regime=MarketRegime.RANGING,
        dominant_regime=MarketRegime.RANGING,
        challenger_version_ids=("strategy_1",),
        strategy_evidence=(
            StrategyEvidence(
                strategy_version_id="strategy_1",
                status=StrategyLifecycle.RESEARCH,
                metrics=make_metrics(),
                experiment_id="experiment_1",
                reason="Research evidence only.",
            ),
        ),
    )

    path = store.write(profile)

    assert path.exists()
    assert store.latest("EURUSD", "M15") == profile

    conflicting = profile.model_copy(update={"latest_regime": MarketRegime.TRENDING_UP})

    with pytest.raises(FileExistsError, match="different content"):
        store.write(conflicting)


def test_change_point_detector_flags_a_causal_return_shift() -> None:
    start = datetime(2026, 8, 3, tzinfo=UTC)
    price = 1.0
    bars: list[MarketBar] = []

    for index in range(35):
        change = 0.0001 if index < 18 else 0.005
        open_price = price
        price *= 1.0 + change
        bars.append(
            MarketBar(
                pair="EURUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * index),
                open=open_price,
                high=max(open_price, price) + 0.0001,
                low=min(open_price, price) - 0.0001,
                close=price,
                tick_volume=100,
                spread_points=1,
            )
        )

    changes = detect_change_points(bars, window=5, threshold=2.0)

    assert changes
    assert changes[0].bar_index >= 18
    assert changes[0].direction == "up"
