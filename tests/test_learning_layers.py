from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai_quant_lab.backtesting import annualization_periods
from ai_quant_lab.institutional.brain import ResearchBrain
from ai_quant_lab.institutional.evolution import evolve_parameters
from ai_quant_lab.institutional.registry import (
    InstitutionalResearchStore,
    RiskDecisionRecord,
    StrategyCandidateRecord,
    StrategyEvolutionProposalRecord,
    StrategyResearchStatus,
)
from ai_quant_lab.institutional.scoring import bonferroni_adjusted_p_value
from ai_quant_lab.institutional.selection import BanditUpdate
from ai_quant_lab.modeling import (
    AgentModelProfile,
    AgentPermissions,
    ModelConfiguration,
    ModelProviderRegistry,
    ModelResponse,
    ModelUsage,
)


def test_timeframe_annualization_and_bonferroni_are_explicit() -> None:
    assert annualization_periods("D1") == 252
    assert annualization_periods("M15") == 252 * 24 * 4
    assert bonferroni_adjusted_p_value(0.01, 7) == pytest.approx(0.07)
    assert bonferroni_adjusted_p_value(0.30, 7) == 1.0

    with pytest.raises(ValueError):
        bonferroni_adjusted_p_value(0.01, 0)


def test_bandit_selection_and_quant_score_update_are_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "institutional.sqlite3"
    store = InstitutionalResearchStore(path)
    strategies = (
        "time_series_momentum",
        "kalman_adaptive_trend",
        "donchian_breakout",
    )
    selected = store.select_bandit_arm(
        campaign_id="campaign_one",
        pair="EURUSD",
        timeframe="M15",
        regime="trending_up",
        strategy_names=strategies,
    )
    replayed = InstitutionalResearchStore(path).select_bandit_arm(
        campaign_id="campaign_one",
        pair="EURUSD",
        timeframe="M15",
        regime="trending_up",
        strategy_names=strategies,
    )

    assert replayed == selected
    assert len(selected.sampled_values) == 3
    assert selected.strategy_name in strategies

    update = BanditUpdate(
        campaign_id="campaign_one",
        pair="EURUSD",
        timeframe="M15",
        regime="trending_up",
        strategy_name=selected.strategy_name,
        quant_score=80.0,
        normalized_reward=0.8,
        gate_passed=True,
    )
    store.apply_bandit_update(update)
    store.apply_bandit_update(update.model_copy(update={"created_at": update.created_at}))
    arms = store.bandit_arms(pair="EURUSD", timeframe="M15", regime="trending_up")
    chosen = next(arm for arm in arms if arm.strategy_name == selected.strategy_name)

    assert chosen.selections == 1
    assert chosen.observations == 1
    assert chosen.alpha == pytest.approx(1.8)
    assert chosen.beta == pytest.approx(1.2)



def test_bandit_reward_must_match_quant_score() -> None:
    with pytest.raises(ValueError, match="quant_score / 100"):
        BanditUpdate(
            campaign_id="campaign_invalid",
            pair="EURUSD",
            timeframe="M15",
            regime="trending_up",
            strategy_name="time_series_momentum",
            quant_score=80.0,
            normalized_reward=0.7,
            gate_passed=False,
        )


def test_institutional_research_has_no_order_send_call_path() -> None:
    package = Path(__file__).parents[1] / "src" / "ai_quant_lab" / "institutional"

    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr != "order_send", f"Forbidden order_send call in {path}"



def test_bandit_outcome_must_match_recorded_selection(tmp_path: Path) -> None:
    store = InstitutionalResearchStore(tmp_path / "institutional.sqlite3")
    selection = store.select_bandit_arm(
        campaign_id="campaign_match",
        pair="EURUSD",
        timeframe="M15",
        regime="trending_up",
        strategy_names=("time_series_momentum", "kalman_adaptive_trend"),
    )
    wrong_strategy = (
        "kalman_adaptive_trend"
        if selection.strategy_name == "time_series_momentum"
        else "time_series_momentum"
    )

    with pytest.raises(ValueError, match="does not match"):
        store.apply_bandit_update(
            BanditUpdate(
                campaign_id="campaign_match",
                pair="EURUSD",
                timeframe="M15",
                regime="trending_up",
                strategy_name=wrong_strategy,
                quant_score=50.0,
                normalized_reward=0.5,
                gate_passed=False,
            )
        )


def test_live_authority_fields_reject_true() -> None:
    with pytest.raises(ValueError):
        RiskDecisionRecord(
            decision_id="risk_invalid",
            campaign_id="campaign_invalid",
            approved_for_shadow=False,
            approved_for_live=True,
            size_multiplier=0.0,
            blockers=("blocked",),
            warnings=(),
            kill_switch_triggered=True,
        )

    with pytest.raises(ValueError):
        StrategyEvolutionProposalRecord(
            proposal_id="proposal_invalid",
            pair="EURUSD",
            timeframe="M15",
            regime="trending_up",
            strategy_name="time_series_momentum",
            parameters={"horizon": 96, "volatility_window": 32, "entry_score": 0.8},
            parent_version_ids=("parent",),
            live_trading_authorized=True,
        )


def test_forge_evolution_mutates_only_validated_same_arm_parents() -> None:
    parents = (
        StrategyCandidateRecord(
            version_id="candidate_a",
            campaign_id="campaign_a",
            pair="EURUSD",
            timeframe="M15",
            strategy_name="time_series_momentum",
            parameters={"horizon": 96, "volatility_window": 32, "entry_score": 0.8},
            status=StrategyResearchStatus.CHALLENGER,
            regime_specialization="trending_up",
            quant_score=80.0,
            reason="passed",
        ),
        StrategyCandidateRecord(
            version_id="candidate_b",
            campaign_id="campaign_b",
            pair="EURUSD",
            timeframe="M15",
            strategy_name="time_series_momentum",
            parameters={"horizon": 72, "volatility_window": 32, "entry_score": 0.65},
            status=StrategyResearchStatus.CHALLENGER,
            regime_specialization="trending_up",
            quant_score=75.0,
            reason="passed",
        ),
    )

    child = evolve_parameters(parents, identity="next_generation")

    assert child is not None
    assert child != parents[0].parameters
    assert child != parents[1].parameters
    assert set(child) == {"horizon", "volatility_window", "entry_score"}


class _FakeProvider:
    key = "fake"

    def complete(self, request: object, configuration: object) -> ModelResponse:
        del configuration
        request_id = getattr(request, "request_id")
        return ModelResponse(
            request_id=request_id,
            provider_key="fake",
            model_name="fake-model",
            text=(
                '{"statement":"Locked momentum parameters should preserve positive '
                'cost-adjusted expectancy in the declared trend regime.",'
                '"economic_rationale":"Slow information diffusion can create persistent '
                'directional returns without changing the deterministic rules.",'
                '"falsification_criteria":["OOS net result is non-positive",'
                '"Walk-forward stability is below threshold",'
                '"Stressed costs remove the edge"],'
                '"compatible_regimes":["trending_up"]}'
            ),
            usage=ModelUsage(),
        )


def test_optional_brain_can_propose_but_cannot_change_locked_parameters() -> None:
    profile = AgentModelProfile(
        agent_key="nova",
        system_prompt="Propose hypotheses only.",
        permissions=AgentPermissions(),
        model=ModelConfiguration(
            provider_key="fake",
            model_name="fake-model",
            input_cost_per_million_usd=1.0,
            output_cost_per_million_usd=1.0,
        ),
    )
    registry = ModelProviderRegistry((_FakeProvider(),))
    brain = ResearchBrain((profile,), registry)
    parameters = {"horizon": 96, "volatility_window": 32, "entry_score": 0.8}
    draft = brain.propose_hypothesis(
        campaign_id="campaign_one",
        pair="EURUSD",
        timeframe="M15",
        regime="trending_up",
        strategy_name="time_series_momentum",
        parameters=parameters,
        history=(),
    )

    assert draft is not None
    assert "trending_up" in draft.compatible_regimes
    assert parameters == {"horizon": 96, "volatility_window": 32, "entry_score": 0.8}
