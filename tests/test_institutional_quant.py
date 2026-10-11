from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_quant_lab.backtesting import run_backtest
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.institutional import (
    DataIntelligenceEngine,
    InstitutionalRegime,
    InstitutionalRegimeEngine,
    PositionRiskInput,
    QuantScoreEvidence,
    calculate_advanced_metrics,
    calculate_quant_score,
    evaluate_portfolio_risk,
)
from ai_quant_lab.strategies import (
    analyze_cointegration_pair,
    build_strategy,
    inverse_volatility_risk_parity,
)
from ai_quant_lab.strategies.blueprints import (
    INSTITUTIONAL_STRATEGY_BLUEPRINTS,
    BlueprintAvailability,
)


def institutional_bars(count: int = 260) -> tuple[MarketBar, ...]:
    start = datetime(2026, 7, 20, tzinfo=UTC)
    bars: list[MarketBar] = []

    for index in range(count):
        wave = ((index % 20) - 10) * 0.000025
        trend = index * 0.000035
        close = 1.10 + trend + wave
        open_price = close - 0.00002
        bars.append(
            MarketBar(
                pair="EURUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * index),
                open=open_price,
                high=max(open_price, close) + 0.00015,
                low=min(open_price, close) - 0.00015,
                close=close,
                tick_volume=1_000 + index,
                spread_points=8,
            )
        )

    return tuple(bars)


def test_data_intelligence_versions_exact_input_and_declares_missing_feeds() -> None:
    bars = institutional_bars()
    report = DataIntelligenceEngine().inspect(bars)
    duplicate = DataIntelligenceEngine().inspect(bars)

    assert duplicate.dataset_version_id == report.dataset_version_id
    assert 0.95 < report.quality_score < 1.0
    assert report.return_outliers == 12
    assert "ohlc" in report.available_capabilities
    assert "order_book" in report.unavailable_capabilities
    assert report.duplicate_timestamps == 0


def test_regime_engine_returns_a_normalized_explainable_distribution() -> None:
    bars = institutional_bars()
    dataset = DataIntelligenceEngine().inspect(bars)
    result = InstitutionalRegimeEngine().assess(bars, dataset)

    assert result.regime is not InstitutionalRegime.INSUFFICIENT_DATA
    assert sum(result.probabilities.values()) == pytest.approx(1.0)
    assert {item.model_name for item in result.evidence} >= {
        "three_state_gaussian_hmm",
        "two_component_gmm_volatility",
        "bayesian_change_point",
        "local_linear_kalman_filter",
    }
    assert result.unavailable_inputs == (
        "cross_asset_risk_score",
        "macro_risk_score",
    )
    hmm_evidence = next(
        item for item in result.evidence if item.model_name == "three_state_gaussian_hmm"
    )
    assert "Baum-Welch" in hmm_evidence.interpretation
    assert hmm_evidence.parameters["calibration_scope"] == "EURUSD:M15"


def test_quant_score_uses_fixed_weights_and_never_authorizes_live() -> None:
    result = run_backtest(institutional_bars(), build_strategy("time_series_momentum"))
    advanced = calculate_advanced_metrics(
        result,
        trial_count=12,
        out_of_sample_stability=0.8,
        parameter_stability=0.75,
        baseline_cost_fraction=0.05,
        stressed_cost_fraction=0.12,
    )
    score = calculate_quant_score(
        result,
        advanced,
        QuantScoreEvidence(
            out_of_sample_stability=0.8,
            regime_robustness=0.7,
            parameter_stability=0.75,
            cost_robustness=0.65,
            statistical_significance=0.7,
            execution_feasibility=0.8,
        ),
    )

    assert sum(component.weight for component in score.components) == pytest.approx(1.0)
    assert score.live_trading_authorized is False
    assert 0 <= advanced.probability_of_backtest_overfitting <= 1


def test_pairs_and_risk_parity_engines_require_real_aligned_series() -> None:
    left = [100 + index * 0.3 + ((index % 5) - 2) * 0.05 for index in range(80)]
    right = [50 + index * 0.15 for index in range(80)]
    diagnostics = analyze_cointegration_pair(left, right)
    allocation = inverse_volatility_risk_parity(
        {
            "EURUSD": (0.001, -0.0005, 0.0007, -0.0002),
            "GBPUSD": (0.0015, -0.001, 0.0004, 0.0002),
        }
    )

    assert diagnostics.observations == 80
    assert sum(allocation.weights.values()) == pytest.approx(1.0)
    assert allocation.live_trading_authorized is False


def test_blueprint_catalog_distinguishes_code_from_missing_data() -> None:
    assert len(INSTITUTIONAL_STRATEGY_BLUEPRINTS) >= 30
    assert any(
        item.availability is BlueprintAvailability.EXECUTABLE
        for item in INSTITUTIONAL_STRATEGY_BLUEPRINTS
    )
    assert any(
        item.availability is BlueprintAvailability.REQUIRES_EXTERNAL_DATA
        for item in INSTITUTIONAL_STRATEGY_BLUEPRINTS
    )


def test_portfolio_risk_blocks_concentrated_correlated_currency_bets() -> None:
    concentrated = evaluate_portfolio_risk(
        tuple(
            PositionRiskInput(
                symbol=symbol,
                direction="buy",
                notional_usd=20_000,
            )
            for symbol in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
        ),
        equity_usd=100_000,
        scenario_returns=(-0.04, -0.03, -0.02, 0.01, 0.02),
    )

    assert concentrated.allows_new_risk is False
    assert concentrated.correlated_bet_count == 4
    assert concentrated.maximum_currency_exposure_fraction == pytest.approx(0.8)
    assert concentrated.size_multiplier == 0
    assert concentrated.live_trading_authorized is False


def test_portfolio_risk_allows_small_offsetting_demo_exposure() -> None:
    diversified = evaluate_portfolio_risk(
        (
            PositionRiskInput(symbol="EURUSD", direction="buy", notional_usd=20_000),
            PositionRiskInput(symbol="GBPUSD", direction="sell", notional_usd=20_000),
        ),
        equity_usd=100_000,
    )

    assert diversified.allows_new_risk is True
    assert diversified.maximum_currency_exposure_fraction == pytest.approx(0.2)
    assert diversified.size_multiplier == pytest.approx(0.75)
