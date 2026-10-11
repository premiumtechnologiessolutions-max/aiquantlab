from __future__ import annotations

from pathlib import Path

from ai_quant_lab.institutional import CampaignStatus, ResearchStageStatus
from tests.test_monitoring_and_voice import make_controller


def _complete_campaign(controller: object) -> object:
    for _ in range(40):
        controller.runtime_tick()  # type: ignore[attr-defined]
        recent = controller.research.store.recent_campaigns(limit=1)  # type: ignore[attr-defined]

        if recent and recent[0].status in {CampaignStatus.COMPLETED, CampaignStatus.FAILED}:
            return recent[0]

    raise AssertionError("Institutional campaign did not reach a terminal state.")


def test_completed_bar_runs_every_agent_stage_and_preserves_failed_attempts(
    tmp_path: Path,
) -> None:
    controller = make_controller(tmp_path, connected=True)
    controller.scan_market()
    campaign = _complete_campaign(controller)

    assert campaign.status is CampaignStatus.COMPLETED
    assert all(stage.status is ResearchStageStatus.COMPLETED for stage in campaign.stages)
    assert {stage.agent_key for stage in campaign.stages} == {
        "vega",
        "iris",
        "oracle",
        "nova",
        "chronos",
        "sentinel",
        "aegis",
        "forge",
        "echo",
    }
    assert campaign.quant_score is not None
    assert campaign.experiment_id is not None
    assert Path(campaign.artifacts["report"]).exists()
    assert "portfolio_risk" in campaign.artifacts
    assert "bandit_selection" in campaign.artifacts
    assert "bandit_update" in campaign.artifacts
    experiment = controller.research.store.experiment(campaign.experiment_id)
    risk = controller.research.store.latest_risk_decision(campaign.campaign_id)
    assert experiment.trial_number == 1
    assert experiment.parameters == campaign.strategy_parameters
    arms = controller.research.store.bandit_arms(
        pair=campaign.pair,
        timeframe=campaign.timeframe,
        regime=controller.research.store.regime(campaign.regime_assessment_id).regime.value,
    )
    assert sum(arm.observations for arm in arms) == 1
    assert risk is not None
    assert risk.approved_for_paper is False
    assert risk.approved_for_live is False
    handoffs = [
        message
        for message in controller.runtime.message_bus.all_messages()
        if message.subject.startswith("Campaign hand-off:")
    ]
    assert len(handoffs) == 9
    assert {message.sender_key for message in handoffs} == {
        "vega",
        "iris",
        "oracle",
        "nova",
        "chronos",
        "sentinel",
        "aegis",
        "forge",
        "echo",
    }
    assert all(stage.tools_used for stage in campaign.stages)
    assert all(stage.produced_outputs for stage in campaign.stages)


def test_same_completed_bar_is_idempotent_and_emergency_stop_is_persistent(
    tmp_path: Path,
) -> None:
    controller = make_controller(tmp_path, connected=True)
    controller.scan_market()
    _complete_campaign(controller)
    initial_count = controller.research.store.counts()["research_campaigns"]
    controller.scan_market()

    assert controller.research.store.counts()["research_campaigns"] == initial_count

    stopped = controller.emergency_stop("Test hard stop")
    assert stopped["control"]["emergency_stop"] is True
    assert stopped["control"]["loop_enabled"] is False

    cleared = controller.reset_emergency_stop()
    assert cleared["control"]["emergency_stop"] is False
    assert cleared["control"]["loop_enabled"] is False
