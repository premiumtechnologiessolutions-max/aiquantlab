from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents import ActivityType, TaskPriority, TaskStatus
from ai_quant_lab.backtesting import BacktestConfig, BacktestResult, run_backtest
from ai_quant_lab.broker import MT5DemoGateway
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.institutional.brain import ResearchBrain
from ai_quant_lab.institutional.data_intelligence import DataIntelligenceEngine
from ai_quant_lab.institutional.regime_engine import (
    InstitutionalRegime,
    InstitutionalRegimeAssessment,
    InstitutionalRegimeEngine,
)
from ai_quant_lab.institutional.registry import (
    CampaignStatus,
    HypothesisRecord,
    InstitutionalExperimentRecord,
    InstitutionalResearchStore,
    ResearchCampaignRecord,
    ResearchStageName,
    ResearchStageRecord,
    ResearchStageStatus,
    RiskDecisionRecord,
    StrategyCandidateRecord,
    StrategyEvolutionProposalRecord,
    StrategyResearchStatus,
)
from ai_quant_lab.institutional.risk_engine import (
    PositionDirection,
    PositionRiskInput,
    evaluate_portfolio_risk,
)
from ai_quant_lab.institutional.scoring import (
    QuantScoreEvidence,
    calculate_advanced_metrics,
    calculate_quant_score,
)
from ai_quant_lab.institutional.evolution import evolve_parameters
from ai_quant_lab.institutional.selection import BanditUpdate, eligible_strategies
from ai_quant_lab.monitoring import DemoMarketMonitor, MarketScanResult
from ai_quant_lab.runtime import LabRuntime
from ai_quant_lab.strategies import (
    StrategyName,
    build_strategy,
    neighboring_variants,
)
from ai_quant_lab.validation import (
    ValidationPolicy,
    assess_parameter_stability,
    run_walk_forward_validation,
)


class ContinuousResearchConfig(BaseModel):
    """Bounded automatic research settings; one campaign per completed bar."""

    model_config = ConfigDict(frozen=True)

    database_path: Path = Path("data/institutional/research.sqlite3")
    artifact_root: Path = Path("data/institutional/artifacts")
    lookback_bars: int = Field(default=600, ge=120, le=10_000)
    minimum_data_quality: float = Field(default=0.80, ge=0, le=1)
    minimum_quant_score: float = Field(default=60.0, ge=0, le=100)
    maximum_drawdown_percent: float = Field(default=20.0, gt=0, le=100)
    purge_bars: int = Field(default=5, ge=1, le=100)
    embargo_bars: int = Field(default=5, ge=1, le=100)
    maximum_spread_points: float = Field(default=50.0, gt=0)


class ContinuousResearchProgram:
    """Restart-safe Atlas-led state machine that produces auditable research work."""

    _STAGES: tuple[tuple[ResearchStageName, str, str], ...] = (
        (
            ResearchStageName.DATA_INTELLIGENCE,
            "vega",
            "Collect, validate, version, and freeze market data",
        ),
        (
            ResearchStageName.REGIME_ANALYSIS,
            "iris",
            "Estimate the current probabilistic market regime",
        ),
        (
            ResearchStageName.MACRO_CAPABILITY_AUDIT,
            "oracle",
            "Audit macro and cross-asset evidence availability",
        ),
        (
            ResearchStageName.HYPOTHESIS_DESIGN,
            "nova",
            "Declare a falsifiable economic hypothesis before testing",
        ),
        (
            ResearchStageName.BACKTEST_VALIDATION,
            "chronos",
            "Run purged, embargoed, cost-stressed validation",
        ),
        (
            ResearchStageName.QUANT_AUDIT,
            "sentinel",
            "Audit leakage, multiple testing, and overfitting evidence",
        ),
        (ResearchStageName.RISK_REVIEW, "aegis", "Apply hard risk blockers and size throttles"),
        (
            ResearchStageName.CHALLENGER_EVOLUTION,
            "forge",
            "Register a bounded challenger or rejection",
        ),
        (ResearchStageName.REPORTING, "echo", "Publish a factual campaign report"),
    )

    def __init__(
        self,
        runtime: LabRuntime,
        monitor: DemoMarketMonitor,
        config: ContinuousResearchConfig | None = None,
        *,
        store: InstitutionalResearchStore | None = None,
        brain: ResearchBrain | None = None,
    ) -> None:
        self.runtime = runtime
        self.monitor = monitor
        self.config = config or ContinuousResearchConfig(
            database_path=runtime.config.operational_database.parent / "institutional.sqlite3",
            artifact_root=runtime.config.report_root.parent / "institutional",
        )
        self.store = store or InstitutionalResearchStore(self.config.database_path)
        self.brain = brain or ResearchBrain()
        self.data_engine = DataIntelligenceEngine()
        self.regime_engine = InstitutionalRegimeEngine()
        self._handlers: dict[ResearchStageName, Callable[[ResearchCampaignRecord], str]] = {
            ResearchStageName.DATA_INTELLIGENCE: self._data_stage,
            ResearchStageName.REGIME_ANALYSIS: self._regime_stage,
            ResearchStageName.MACRO_CAPABILITY_AUDIT: self._macro_stage,
            ResearchStageName.HYPOTHESIS_DESIGN: self._hypothesis_stage,
            ResearchStageName.BACKTEST_VALIDATION: self._backtest_stage,
            ResearchStageName.QUANT_AUDIT: self._audit_stage,
            ResearchStageName.RISK_REVIEW: self._risk_stage,
            ResearchStageName.CHALLENGER_EVOLUTION: self._forge_stage,
            ResearchStageName.REPORTING: self._report_stage,
        }

    def tick(self) -> dict[str, object]:
        """Advance at most one state transition, keeping work observable and bounded."""

        control = self.store.control()

        if control.emergency_stop:
            self._pause_active("Emergency stop is active.")
            return self.overview()

        if not control.loop_enabled:
            self._pause_active("Continuous research is paused by the operator.")
            return self.overview()

        campaign = self.store.active_campaign()

        if campaign is None:
            campaign = self._discover_campaign()

            if campaign is None:
                return self.overview()

        if campaign.status is CampaignStatus.PAUSED:
            campaign = self._resume_campaign(campaign)

        self._advance(campaign)

        return self.overview()

    def start(self) -> dict[str, object]:
        """Enable automatic research; it still waits for a real completed market bar."""

        self.store.set_control(
            loop_enabled=True,
            emergency_stop=False,
            reason="Continuous institutional research enabled by the operator.",
        )
        return self.overview()

    def pause(self) -> dict[str, object]:
        """Pause research safely without deleting campaign state."""

        self.store.set_control(
            loop_enabled=False,
            reason="Continuous institutional research paused by the operator.",
        )
        self._pause_active("Paused by the operator; evidence and progress were preserved.")
        return self.overview()

    def emergency_stop(self, reason: str = "Operator emergency stop.") -> dict[str, object]:
        """Trigger the global research and execution kill switch."""

        self.store.set_control(
            loop_enabled=False,
            emergency_stop=True,
            reason=reason,
        )
        self._pause_active(reason)
        self.runtime.journal.record(
            event_type=ActivityType.JOB_FAILED,
            actor_key="aegis",
            message=f"Institutional emergency stop triggered: {reason}",
        )
        return self.overview()

    def reset_emergency_stop(self) -> dict[str, object]:
        """Clear the kill switch without enabling the loop automatically."""

        self.store.set_control(
            loop_enabled=False,
            emergency_stop=False,
            reason="Emergency stop cleared; research remains paused until explicitly started.",
        )
        return self.overview()

    def overview(self) -> dict[str, object]:
        """Return concise command-center state for the local dashboard."""

        control = self.store.control()
        active = self.store.active_campaign()
        recent = self.store.recent_campaigns(limit=10)

        return {
            "control": control.model_dump(mode="json"),
            "active_campaign": active.model_dump(mode="json") if active else None,
            "recent_campaigns": [item.model_dump(mode="json") for item in recent],
            "registry_counts": self.store.counts(),
            "cadence": "one campaign per pair/timeframe completed bar",
            "automatic_broker_orders": False,
            "paper_promotion_requires_human": True,
        }

    def _discover_campaign(self) -> ResearchCampaignRecord | None:
        scans = self.monitor.store.recent(limit=50)

        for scan in scans:
            source_key = _source_bar_key(scan)

            if self.store.campaign_for_source(source_key) is not None:
                continue

            return self._create_campaign(scan, source_key)

        return None

    def _create_campaign(
        self,
        scan: MarketScanResult,
        source_key: str,
    ) -> ResearchCampaignRecord:
        digest = _short_hash(source_key)
        campaign_id = f"campaign_{digest}"
        root_task_id = f"institutional_{digest}"
        stages = tuple(
            _research_stage_record(name, agent_key)
            for name, agent_key, _ in self._STAGES
        )
        campaign = ResearchCampaignRecord(
            campaign_id=campaign_id,
            source_bar_key=source_key,
            pair=scan.pair,
            timeframe=scan.timeframe,
            latest_bar_at=scan.latest_bar_at,
            title=f"{scan.pair} {scan.timeframe} Institutional Regime Research",
            status=CampaignStatus.ACTIVE,
            root_task_id=root_task_id,
            stages=stages,
        )
        board = self.runtime.task_board

        try:
            board.get_task(root_task_id)
        except KeyError:
            created = board.create_task(
                task_id=root_task_id,
                title=campaign.title,
                description=(
                    "Atlas coordinates a reproducible research campaign. "
                    "No real-money broker order is permitted."
                ),
                priority=TaskPriority.HIGH,
                required_agent_key="atlas",
                tags=("institutional", "automatic", "research_only", campaign_id),
            )
            board.assign_task(created.task_id, "atlas")
            board.start_task(created.task_id, note="Atlas is coordinating the evidence chain.")

        campaign = self._assign_current_stage(campaign)
        self.store.save_campaign(campaign)
        self.runtime.journal.record(
            event_type=ActivityType.JOB_STARTED,
            actor_key="atlas",
            message=f"Started institutional campaign {campaign.campaign_id} for {scan.pair}.",
            metadata={"campaign_id": campaign.campaign_id, "source_bar_key": source_key},
        )

        return campaign

    def _advance(self, campaign: ResearchCampaignRecord) -> None:
        if campaign.current_stage_index >= len(campaign.stages):
            self._finish_campaign(campaign)
            return

        stage = campaign.stages[campaign.current_stage_index]

        if stage.task_id is None:
            campaign = self._assign_current_stage(campaign)
            self.store.save_campaign(campaign)
            return

        board = self.runtime.task_board
        task = board.get_task(stage.task_id)

        if task.status is TaskStatus.ASSIGNED:
            board.start_task(
                task.task_id, note=f"Executing {stage.name.value} with recorded inputs."
            )
            board.update_progress(
                task.task_id,
                15.0,
                note="Inputs resolved; deterministic evidence stage is running.",
            )
            self.store.save_campaign(
                self._replace_stage(
                    campaign,
                    stage.model_copy(
                        update={
                            "status": ResearchStageStatus.RUNNING,
                            "progress_percent": 15.0,
                            "started_at": datetime.now(UTC),
                        }
                    ),
                )
            )
            return

        if task.status in {TaskStatus.RUNNING, TaskStatus.WAITING}:
            try:
                summary = self._handlers[stage.name](campaign)
            except Exception as error:  # noqa: BLE001 - failure is persisted and isolated
                message = f"{type(error).__name__}: {error}"
                board.fail_task(task.task_id, error_message=message)
                failed_stage = stage.model_copy(
                    update={
                        "status": ResearchStageStatus.FAILED,
                        "progress_percent": task.progress_percent,
                        "error": message,
                        "completed_at": datetime.now(UTC),
                    }
                )
                campaign = self._replace_stage(campaign, failed_stage).model_copy(
                    update={
                        "status": CampaignStatus.FAILED,
                        "failure_reasons": (*campaign.failure_reasons, message),
                        "summary": f"Campaign stopped at {stage.name.value}.",
                        "updated_at": datetime.now(UTC),
                    }
                )
                self.store.save_campaign(campaign)
                root = board.get_task(campaign.root_task_id)

                if root.is_active:
                    board.fail_task(root.task_id, error_message=message)

                self.runtime.journal.record(
                    event_type=ActivityType.JOB_FAILED,
                    actor_key=stage.agent_key,
                    message=f"Campaign {campaign.campaign_id} failed: {message}",
                )
                return

            refreshed = self.store.campaign_for_source(campaign.source_bar_key)

            if refreshed is not None:
                campaign = refreshed
                stage = campaign.stages[campaign.current_stage_index]

            board.complete_task(task.task_id, result_summary=summary)
            completed_stage = stage.model_copy(
                update={
                    "status": ResearchStageStatus.COMPLETED,
                    "progress_percent": 100.0,
                    "produced_outputs": (summary,),
                    "summary": summary,
                    "completed_at": datetime.now(UTC),
                }
            )
            campaign = self._replace_stage(campaign, completed_stage).model_copy(
                update={
                    "current_stage_index": campaign.current_stage_index + 1,
                    "updated_at": datetime.now(UTC),
                }
            )

            if campaign.current_stage_index < len(campaign.stages):
                campaign = self._assign_current_stage(campaign)

            self._send_handoff(campaign, completed_stage, summary)
            self.store.save_campaign(campaign)

            if campaign.current_stage_index >= len(campaign.stages):
                self._finish_campaign(campaign)

    def _send_handoff(
        self,
        campaign: ResearchCampaignRecord,
        completed_stage: ResearchStageRecord,
        summary: str,
    ) -> None:
        """Record one idempotent evidence hand-off between named agents."""

        if campaign.current_stage_index < len(campaign.stages):
            recipient = campaign.stages[campaign.current_stage_index].agent_key
            next_task_id = campaign.stages[campaign.current_stage_index].task_id
        else:
            recipient = "atlas"
            next_task_id = campaign.root_task_id

        message_id = f"handoff_{campaign.campaign_id}_{completed_stage.name.value}"

        try:
            self.runtime.message_bus.send(
                message_id=message_id,
                sender_key=completed_stage.agent_key,
                recipient_key=recipient,
                subject=f"Campaign hand-off: {completed_stage.name.value}",
                body=summary,
                task_id=next_task_id,
            )
        except ValueError as error:
            if "already exists" not in str(error):
                raise

    def _assign_current_stage(
        self,
        campaign: ResearchCampaignRecord,
    ) -> ResearchCampaignRecord:
        if campaign.current_stage_index >= len(campaign.stages):
            return campaign

        stage = campaign.stages[campaign.current_stage_index]

        if stage.task_id is not None:
            return campaign

        _, agent_key, title = self._STAGES[campaign.current_stage_index]
        task_id = f"{campaign.campaign_id}_{stage.name.value}"
        board = self.runtime.task_board
        created = board.create_task(
            task_id=task_id,
            title=title,
            description=f"Evidence stage {stage.name.value} for {campaign.campaign_id}.",
            priority=TaskPriority.HIGH,
            required_agent_key=agent_key,
            parent_task_id=campaign.root_task_id,
            tags=(
                "institutional",
                "continuous_research",
                "research_only",
                campaign.campaign_id,
            ),
        )
        board.assign_task(created.task_id, agent_key)
        assigned = stage.model_copy(
            update={"task_id": task_id, "status": ResearchStageStatus.ASSIGNED}
        )

        return self._replace_stage(campaign, assigned)

    def _replace_stage(
        self,
        campaign: ResearchCampaignRecord,
        replacement: ResearchStageRecord,
    ) -> ResearchCampaignRecord:
        stages = list(campaign.stages)
        index = next(index for index, stage in enumerate(stages) if stage.name is replacement.name)
        stages[index] = replacement

        return campaign.model_copy(
            update={"stages": tuple(stages), "updated_at": datetime.now(UTC)}
        )

    def _pause_active(self, reason: str) -> None:
        campaign = self.store.active_campaign()

        if campaign is None or campaign.status is CampaignStatus.PAUSED:
            return

        if campaign.current_stage_index < len(campaign.stages):
            stage = campaign.stages[campaign.current_stage_index]

            if stage.task_id is not None:
                task = self.runtime.task_board.get_task(stage.task_id)

                if task.status is TaskStatus.RUNNING:
                    self.runtime.task_board.wait_task(task.task_id, note=reason)

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "status": CampaignStatus.PAUSED,
                    "summary": reason,
                    "updated_at": datetime.now(UTC),
                }
            )
        )

    def _resume_campaign(self, campaign: ResearchCampaignRecord) -> ResearchCampaignRecord:
        updated = campaign.model_copy(
            update={"status": CampaignStatus.ACTIVE, "updated_at": datetime.now(UTC)}
        )
        self.store.save_campaign(updated)
        return updated

    def _finish_campaign(self, campaign: ResearchCampaignRecord) -> None:
        if campaign.status is CampaignStatus.COMPLETED:
            return

        root = self.runtime.task_board.get_task(campaign.root_task_id)

        if root.is_active:
            self.runtime.task_board.complete_task(
                root.task_id,
                result_summary="Full institutional evidence chain completed; no live order sent.",
            )

        updated = campaign.model_copy(
            update={
                "status": CampaignStatus.COMPLETED,
                "summary": (
                    f"Completed with Quant Score {campaign.quant_score:.1f}; "
                    f"risk decision {campaign.risk_decision}."
                    if campaign.quant_score is not None
                    else "Completed without a promotable candidate."
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.save_campaign(updated)
        self.runtime.journal.record(
            event_type=ActivityType.JOB_COMPLETED,
            actor_key="atlas",
            message=f"Completed institutional campaign {campaign.campaign_id}.",
            metadata={"campaign_id": campaign.campaign_id},
        )

    def _data_stage(self, campaign: ResearchCampaignRecord) -> str:
        bars = self._live_bars(campaign)
        report = self.data_engine.inspect(bars, source="mt5_demo_completed_bars")
        directory = self._campaign_directory(campaign)
        snapshot_path = directory / "dataset.json"
        _atomic_write(
            snapshot_path,
            json.dumps([bar.model_dump(mode="json") for bar in bars], ensure_ascii=False),
        )
        self.store.record_dataset(report)
        campaign = campaign.model_copy(
            update={
                "dataset_version_id": report.dataset_version_id,
                "artifacts": {**campaign.artifacts, "dataset_snapshot": str(snapshot_path)},
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.save_campaign(campaign)

        if report.duplicate_timestamps or report.non_monotonic_rows:
            raise RuntimeError("Dataset failed duplicate or chronological integrity gates.")

        return (
            f"Vega froze {report.bar_count} bars as {report.dataset_version_id}; "
            f"quality {report.quality_score:.1%}, missing {report.missing_ratio:.2%}."
        )

    def _regime_stage(self, campaign: ResearchCampaignRecord) -> str:
        bars = self._frozen_bars(campaign)
        dataset = self.store.dataset(_required(campaign.dataset_version_id, "dataset"))
        assessment = self.regime_engine.assess(bars, dataset)
        self.store.record_regime(assessment)
        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "regime_assessment_id": assessment.assessment_id,
                    "artifacts": {
                        **campaign.artifacts,
                        "regime_assessment": assessment.model_dump_json(indent=2),
                    },
                    "updated_at": datetime.now(UTC),
                }
            )
        )

        return (
            f"Iris classified {assessment.regime.value} at {assessment.confidence:.1%} "
            f"confidence; transition probability {assessment.transition_probability:.1%}."
        )

    def _macro_stage(self, campaign: ResearchCampaignRecord) -> str:
        assessment = self.store.regime(
            _required(campaign.regime_assessment_id, "regime assessment")
        )

        if assessment.unavailable_inputs:
            summary = (
                "Oracle recorded that macro/cross-asset feeds are unavailable; "
                "risk-on/off claims were excluded instead of invented."
            )
        else:
            summary = "Oracle verified macro and cross-asset inputs used by the regime engine."

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "artifacts": {
                        **campaign.artifacts,
                        "macro_capability_audit": json.dumps(
                            {
                                "unavailable_inputs": assessment.unavailable_inputs,
                                "invented_values": False,
                            }
                        ),
                    },
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return summary

    def _hypothesis_stage(self, campaign: ResearchCampaignRecord) -> str:
        regime = self.store.regime(_required(campaign.regime_assessment_id, "regime assessment"))
        selection = self.store.select_bandit_arm(
            campaign_id=campaign.campaign_id,
            pair=campaign.pair,
            timeframe=campaign.timeframe,
            regime=regime.regime.value,
            strategy_names=eligible_strategies(regime.regime),
        )
        strategy_name = selection.strategy_name
        proposal = self.store.pending_evolution_proposal(
            pair=campaign.pair,
            timeframe=campaign.timeframe,
            regime=regime.regime.value,
            strategy_name=strategy_name,
        )

        if proposal is not None:
            proposal = self.store.consume_evolution_proposal(
                proposal.proposal_id,
                campaign_id=campaign.campaign_id,
            )
            parameters = proposal.parameters
            proposal_id: str | None = proposal.proposal_id
        else:
            parameters = dict(build_strategy(strategy_name).descriptor.parameters)
            proposal_id = None

        locked_identity = json.dumps(
            {
                "campaign": campaign.campaign_id,
                "strategy": strategy_name,
                "parameters": parameters,
            },
            sort_keys=True,
        )
        hypothesis_id = f"hypothesis_{_short_hash(locked_identity)}"
        history_rows: list[dict[str, object]] = []

        for item in self.store.recent_campaigns(limit=12):
            if item.campaign_id == campaign.campaign_id or item.hypothesis_id is None:
                continue

            recorded = self.store.hypothesis(item.hypothesis_id)
            history_rows.append(
                {
                    "campaign_id": item.campaign_id,
                    "hypothesis_id": recorded.hypothesis_id,
                    "strategy_name": recorded.strategy_name,
                    "locked_parameters": recorded.parameters,
                    "statement": recorded.statement,
                    "economic_rationale": recorded.economic_rationale,
                    "quant_score": item.quant_score,
                    "risk_decision": item.risk_decision,
                    "failure_reasons": item.failure_reasons,
                }
            )

        history = tuple(history_rows)
        draft = self.brain.propose_hypothesis(
            campaign_id=campaign.campaign_id,
            pair=campaign.pair,
            timeframe=campaign.timeframe,
            regime=regime.regime.value,
            strategy_name=strategy_name,
            parameters=parameters,
            history=history,
        )
        hypothesis = (
            HypothesisRecord(
                hypothesis_id=hypothesis_id,
                campaign_id=campaign.campaign_id,
                strategy_name=strategy_name,
                parameters=parameters,
                statement=draft.statement,
                economic_rationale=draft.economic_rationale,
                falsification_criteria=draft.falsification_criteria,
                compatible_regimes=draft.compatible_regimes,
            )
            if draft is not None
            else _hypothesis(
                hypothesis_id,
                campaign,
                strategy_name,
                parameters,
                regime,
            )
        )
        self.store.record_hypothesis(hypothesis)
        artifacts = {
            **campaign.artifacts,
            "hypothesis": hypothesis.model_dump_json(indent=2),
            "hypothesis_origin": "bounded_llm" if draft is not None else "deterministic_fallback",
            "bandit_selection": selection.model_dump_json(indent=2),
        }

        if proposal is not None:
            artifacts["evolution_input"] = proposal.model_dump_json(indent=2)

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "strategy_name": strategy_name,
                    "strategy_parameters": parameters,
                    "evolution_proposal_id": proposal_id,
                    "artifacts": artifacts,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        source = "genetic proposal" if proposal_id else "default parameter seed"
        return (
            f"Nova froze {hypothesis.hypothesis_id} for {strategy_name} from {source}; "
            "the Bandit choice and parameters are locked before OOS."
        )

    def _backtest_stage(self, campaign: ResearchCampaignRecord) -> str:
        bars = self._frozen_bars(campaign)
        strategy_name = _strategy_name(_required(campaign.strategy_name, "strategy"))
        parameters = dict(campaign.strategy_parameters)
        strategy = build_strategy(strategy_name, parameters)
        split = max(60, int(len(bars) * 0.60))
        oos_start = min(len(bars) - 2, split + self.config.embargo_bars)
        in_sample_bars = bars[:split]
        out_of_sample_bars = bars[oos_start:]

        if len(in_sample_bars) < 60 or len(out_of_sample_bars) < 40:
            raise RuntimeError("Frozen dataset is too short for embargoed out-of-sample testing.")

        in_sample = run_backtest(in_sample_bars, strategy)
        out_of_sample = run_backtest(
            out_of_sample_bars,
            build_strategy(strategy_name, parameters),
        )
        stressed = run_backtest(
            out_of_sample_bars,
            build_strategy(strategy_name, parameters),
            BacktestConfig(slippage_points=5.0, commission_per_side=0.50),
        )
        variants = tuple(
            run_backtest(in_sample_bars, variant)
            for variant in neighboring_variants(strategy_name, strategy.descriptor.parameters)
        )
        parameter_summary = assess_parameter_stability(
            variants,
            minimum_profitable_fraction=0.60,
            maximum_return_range_percent=50.0,
        )
        regime_robustness = self._regime_robustness(
            out_of_sample_bars,
            strategy_name,
            parameters,
        )
        policy = ValidationPolicy(
            minimum_trades=3,
            minimum_profit_factor=1.0,
            minimum_sharpe_ratio=0.0,
            maximum_drawdown_percent=self.config.maximum_drawdown_percent,
        )

        try:
            walk_forward = run_walk_forward_validation(
                bars,
                strategy_factory=lambda: build_strategy(strategy_name, parameters),
                train_size=max(60, len(bars) // 2),
                test_size=max(40, len(bars) // 5),
                purge_bars=self.config.purge_bars,
                backtest_config=BacktestConfig(),
                validation_policy=policy,
                minimum_pass_fraction=0.60,
            )
            walk_forward_fraction = walk_forward.pass_fraction
        except ValueError:
            walk_forward_fraction = 0.0

        sign_consistency = float(
            in_sample.metrics.net_return_percent * out_of_sample.metrics.net_return_percent > 0
        )
        oos_profitability = float(out_of_sample.metrics.net_profit > 0)
        oos_stability = (sign_consistency + oos_profitability + walk_forward_fraction) / 3.0
        parameter_stability = parameter_summary.profitable_fraction
        baseline_cost_fraction = _cost_fraction(out_of_sample)
        stressed_cost_fraction = _cost_fraction(stressed)
        cost_robustness = max(
            0.0,
            min(
                1.0,
                0.5 * float(stressed.metrics.net_profit > 0)
                + 0.5
                * max(
                    0.0,
                    1.0
                    - abs(
                        stressed.metrics.net_return_percent
                        - out_of_sample.metrics.net_return_percent
                    )
                    / max(1.0, abs(out_of_sample.metrics.net_return_percent)),
                ),
            ),
        )
        trial_number = self.store.trial_count() + 1
        execution_feasibility = max(
            0.0,
            min(
                1.0,
                1.0
                - baseline_cost_fraction
                - min(0.5, len(out_of_sample.trades) / max(1, len(out_of_sample_bars)) / 2),
            ),
        )
        provisional_advanced = calculate_advanced_metrics(
            out_of_sample,
            trial_count=trial_number,
            out_of_sample_stability=oos_stability,
            parameter_stability=parameter_stability,
            baseline_cost_fraction=baseline_cost_fraction,
            stressed_cost_fraction=stressed_cost_fraction,
        )
        statistical_significance = max(
            0.0,
            1.0 - provisional_advanced.multiple_testing_adjusted_p_value,
        )
        evidence = QuantScoreEvidence(
            out_of_sample_stability=oos_stability,
            regime_robustness=regime_robustness,
            parameter_stability=parameter_stability,
            cost_robustness=cost_robustness,
            statistical_significance=statistical_significance,
            execution_feasibility=execution_feasibility,
        )
        quant_score = calculate_quant_score(
            out_of_sample,
            provisional_advanced,
            evidence,
            threshold=self.config.minimum_quant_score,
        )
        experiment_id = f"experiment_{_short_hash(campaign.campaign_id + str(trial_number))}"
        failure_reasons = tuple(
            reason
            for failed, reason in (
                (
                    out_of_sample.metrics.net_profit <= 0,
                    "Out-of-sample net result was not positive.",
                ),
                (oos_stability < 0.60, "Out-of-sample/walk-forward stability was below 60%."),
                (parameter_stability < 0.60, "Neighboring parameter stability was below 60%."),
                (cost_robustness < 0.50, "Candidate did not survive stressed costs."),
                (
                    provisional_advanced.probability_of_backtest_overfitting > 0.50,
                    "Estimated probability of backtest overfitting exceeded 50%.",
                ),
                (not quant_score.passes_research_threshold, "Quant Score was below threshold."),
            )
            if failed
        )
        experiment = InstitutionalExperimentRecord(
            experiment_id=experiment_id,
            campaign_id=campaign.campaign_id,
            hypothesis_id=_required(campaign.hypothesis_id, "hypothesis"),
            dataset_version_id=_required(campaign.dataset_version_id, "dataset"),
            strategy_name=strategy_name,
            parameters=strategy.descriptor.parameters,
            trial_number=trial_number,
            in_sample_metrics=_metrics_payload(in_sample),
            out_of_sample_metrics=_metrics_payload(out_of_sample),
            stressed_metrics=_metrics_payload(stressed),
            advanced_metrics=provisional_advanced,
            score_evidence=evidence,
            quant_score=quant_score,
            purge_bars=self.config.purge_bars,
            embargo_bars=self.config.embargo_bars,
            failure_reasons=failure_reasons,
        )
        self.store.record_experiment(experiment)
        result_path = self._campaign_directory(campaign) / "experiment.json"
        _atomic_write(
            result_path,
            json.dumps(
                {
                    "registry_record": experiment.model_dump(mode="json"),
                    "in_sample": in_sample.model_dump(mode="json"),
                    "out_of_sample": out_of_sample.model_dump(mode="json"),
                    "cost_stress": stressed.model_dump(mode="json"),
                    "walk_forward_pass_fraction": walk_forward_fraction,
                    "parameter_stability": parameter_summary.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "experiment_id": experiment_id,
                    "quant_score": quant_score.total,
                    "failure_reasons": failure_reasons,
                    "artifacts": {**campaign.artifacts, "experiment": str(result_path)},
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return (
            f"Chronos completed trial {trial_number}: OOS return "
            f"{out_of_sample.metrics.net_return_percent:.2f}%, Quant Score "
            f"{quant_score.total:.1f}, {len(failure_reasons)} failure reasons."
        )

    def _audit_stage(self, campaign: ResearchCampaignRecord) -> str:
        experiment = self.store.experiment(_required(campaign.experiment_id, "experiment"))
        audit = {
            "look_ahead_execution_lag_bars": 1,
            "purge_bars": experiment.purge_bars,
            "embargo_bars": experiment.embargo_bars,
            "dataset_version_locked": True,
            "parameters_locked_before_test": True,
            "test_data_reused_after_viewing": experiment.attempted_after_viewing_test_data,
            "trial_number": experiment.trial_number,
            "multiple_testing_adjusted_p_value": (
                experiment.advanced_metrics.multiple_testing_adjusted_p_value
            ),
            "probability_of_backtest_overfitting": (
                experiment.advanced_metrics.probability_of_backtest_overfitting
            ),
            "failed_attempts_preserved": True,
        }
        commentary = self.brain.audit_commentary(
            campaign_id=campaign.campaign_id,
            audit=audit,
            failure_reasons=experiment.failure_reasons,
        )
        audit_artifacts = {
            **campaign.artifacts,
            "sentinel_audit": json.dumps(audit, indent=2),
        }

        if commentary is not None:
            audit_artifacts["sentinel_commentary"] = commentary

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "artifacts": audit_artifacts,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return (
            "Sentinel preserved all attempts and audited one-bar lag, purge, embargo, "
            f"multiple testing, and PBO {audit['probability_of_backtest_overfitting']:.1%}."
        )

    def _risk_stage(self, campaign: ResearchCampaignRecord) -> str:
        dataset = self.store.dataset(_required(campaign.dataset_version_id, "dataset"))
        regime = self.store.regime(_required(campaign.regime_assessment_id, "regime assessment"))
        experiment = self.store.experiment(_required(campaign.experiment_id, "experiment"))
        control = self.store.control()
        gateway = cast(MT5DemoGateway, self.monitor.gateway)
        account_status = gateway.status()
        blockers: list[str] = []
        warnings: list[str] = []

        if not account_status.connected or account_status.account is None:
            raise RuntimeError("Verified Demo account state is unavailable for portfolio risk.")

        positions = gateway.positions()
        risk_inputs = tuple(
            PositionRiskInput(
                symbol=position.symbol,
                direction=PositionDirection(position.side.value),
                notional_usd=_position_notional_usd(
                    position.symbol,
                    position.volume_lots,
                    position.current_price,
                ),
            )
            for position in positions
        )
        portfolio = evaluate_portfolio_risk(
            risk_inputs,
            equity_usd=account_status.account.equity,
            scenario_returns=_candidate_scenario_returns(campaign),
        )
        blockers.extend(portfolio.blockers)
        warnings.extend(portfolio.warnings)

        if account_status.account.currency != "USD":
            warnings.append(
                "Portfolio notionals are USD-normalized while the Demo account uses "
                f"{account_status.account.currency}."
            )

        if control.emergency_stop:
            blockers.append("Global emergency stop is active.")
        if dataset.quality_score < self.config.minimum_data_quality:
            blockers.append("Dataset quality is below the configured minimum.")
        if dataset.maximum_spread_points > self.config.maximum_spread_points:
            blockers.append("Observed spread exceeded the hard liquidity limit.")
        if (
            float(experiment.out_of_sample_metrics["maximum_drawdown_percent"])
            > self.config.maximum_drawdown_percent
        ):
            blockers.append("Out-of-sample drawdown exceeded the strategy limit.")
        if not experiment.quant_score.passes_research_threshold:
            blockers.append("Quant Score did not pass the research threshold.")
        if experiment.score_evidence.out_of_sample_stability < 0.60:
            blockers.append("Out-of-sample stability is below 60%.")

        size_multiplier = 1.0
        size_multiplier *= portfolio.size_multiplier

        if regime.regime in {
            InstitutionalRegime.HIGH_VOLATILITY,
            InstitutionalRegime.TRANSITION,
        }:
            size_multiplier *= 0.65
            warnings.append("Size reduced 35% for volatility or transition uncertainty.")
        if regime.regime is InstitutionalRegime.LIQUIDITY_STRESS:
            blockers.append("Liquidity stress regime blocks new risk.")
        if blockers:
            size_multiplier = 0.0

        decision = RiskDecisionRecord(
            decision_id=f"risk_{_short_hash(campaign.campaign_id)}",
            campaign_id=campaign.campaign_id,
            approved_for_shadow=not blockers,
            size_multiplier=size_multiplier,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            kill_switch_triggered=control.emergency_stop,
            portfolio_gross_leverage=portfolio.gross_leverage,
            portfolio_cvar_95_fraction=portfolio.portfolio_cvar_95_fraction,
            maximum_currency_exposure_fraction=(
                portfolio.maximum_currency_exposure_fraction
            ),
            correlated_bet_count=portfolio.correlated_bet_count,
        )
        self.store.record_risk_decision(decision)
        decision_text = "approved_for_shadow" if decision.approved_for_shadow else "rejected"
        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "risk_decision": decision_text,
                    "artifacts": {
                        **campaign.artifacts,
                        "risk_decision": decision.model_dump_json(indent=2),
                        "portfolio_risk": portfolio.model_dump_json(indent=2),
                    },
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return (
            f"Aegis decision: {decision_text}; size multiplier {size_multiplier:.2f}; "
            f"gross leverage {portfolio.gross_leverage:.2f}; {len(blockers)} hard blockers. "
            "Paper/live remain unauthorized."
        )

    def _forge_stage(self, campaign: ResearchCampaignRecord) -> str:
        experiment = self.store.experiment(_required(campaign.experiment_id, "experiment"))
        risk = self.store.latest_risk_decision(campaign.campaign_id)

        if risk is None:
            raise RuntimeError("Aegis decision is missing.")

        regime = self.store.regime(_required(campaign.regime_assessment_id, "regime assessment"))
        status = (
            StrategyResearchStatus.CHALLENGER
            if risk.approved_for_shadow and experiment.quant_score.passes_research_threshold
            else StrategyResearchStatus.REJECTED
        )
        parent_version_id: str | None = None

        if campaign.evolution_proposal_id is not None:
            proposal = self.store.evolution_proposal(campaign.evolution_proposal_id)
            parent_version_id = (
                proposal.parent_version_ids[0]
                if proposal.parent_version_ids
                else None
            )

        identity = json.dumps(
            {
                "strategy": experiment.strategy_name,
                "parameters": experiment.parameters,
                "dataset": experiment.dataset_version_id,
                "experiment": experiment.experiment_id,
            },
            sort_keys=True,
        )
        version_id = f"candidate_{_short_hash(identity)}"
        candidate = StrategyCandidateRecord(
            version_id=version_id,
            campaign_id=campaign.campaign_id,
            parent_version_id=parent_version_id,
            pair=campaign.pair,
            timeframe=campaign.timeframe,
            strategy_name=experiment.strategy_name,
            parameters=experiment.parameters,
            status=status,
            regime_specialization=regime.regime.value,
            quant_score=experiment.quant_score.total,
            reason=(
                "Passed independent research and Aegis shadow gates."
                if status is StrategyResearchStatus.CHALLENGER
                else "; ".join(experiment.failure_reasons or risk.blockers)
            ),
        )
        self.store.record_candidate(candidate)
        bandit_update = self.store.apply_bandit_update(
            BanditUpdate(
                campaign_id=campaign.campaign_id,
                pair=campaign.pair,
                timeframe=campaign.timeframe,
                regime=regime.regime,
                strategy_name=_strategy_name(experiment.strategy_name),
                quant_score=experiment.quant_score.total,
                normalized_reward=experiment.quant_score.total / 100.0,
                gate_passed=status is StrategyResearchStatus.CHALLENGER,
            )
        )
        artifacts = {
            **campaign.artifacts,
            "candidate": candidate.model_dump_json(indent=2),
            "bandit_update": bandit_update.model_dump_json(indent=2),
        }
        proposal_text = "no child queued"

        if status is StrategyResearchStatus.CHALLENGER:
            parents = self.store.top_challengers(
                pair=campaign.pair,
                timeframe=campaign.timeframe,
                regime=regime.regime.value,
                strategy_name=experiment.strategy_name,
                limit=2,
            )
            child_parameters = evolve_parameters(
                parents,
                identity=f"{campaign.campaign_id}|{version_id}",
            )

            if child_parameters is not None and child_parameters != experiment.parameters:
                proposal_identity = json.dumps(
                    {
                        "pair": campaign.pair,
                        "timeframe": campaign.timeframe,
                        "regime": regime.regime.value,
                        "strategy": experiment.strategy_name,
                        "parameters": child_parameters,
                        "parents": [parent.version_id for parent in parents],
                    },
                    sort_keys=True,
                )
                proposal = StrategyEvolutionProposalRecord(
                    proposal_id=f"proposal_{_short_hash(proposal_identity)}",
                    pair=campaign.pair,
                    timeframe=campaign.timeframe,
                    regime=regime.regime.value,
                    strategy_name=experiment.strategy_name,
                    parameters=child_parameters,
                    parent_version_ids=tuple(parent.version_id for parent in parents),
                )
                self.store.record_evolution_proposal(proposal)
                artifacts["evolution_output"] = proposal.model_dump_json(indent=2)
                proposal_text = f"queued genetic child {proposal.proposal_id} as an untested idea"

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "candidate_version_id": version_id,
                    "artifacts": artifacts,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return (
            f"Forge registered {version_id} as {status.value} and {proposal_text}; "
            "every child must re-enter Nova → Chronos → Sentinel → Aegis before challenger status."
        )

    def _report_stage(self, campaign: ResearchCampaignRecord) -> str:
        experiment = self.store.experiment(_required(campaign.experiment_id, "experiment"))
        risk = self.store.latest_risk_decision(campaign.campaign_id)
        regime = self.store.regime(_required(campaign.regime_assessment_id, "regime assessment"))
        report_path = self._campaign_directory(campaign) / "REPORT.md"
        failure_rows = (
            "\n".join(f"- {reason}" for reason in experiment.failure_reasons)
            or "- None recorded at the research threshold."
        )
        facts = {
            "campaign_id": campaign.campaign_id,
            "dataset_version_id": campaign.dataset_version_id,
            "regime": regime.regime.value,
            "regime_confidence": regime.confidence,
            "hypothesis_id": campaign.hypothesis_id,
            "strategy_name": experiment.strategy_name,
            "locked_parameters": experiment.parameters,
            "trial_number": experiment.trial_number,
            "quant_score": experiment.quant_score.total,
            "approved_for_shadow": bool(risk and risk.approved_for_shadow),
            "approved_for_paper": False,
            "approved_for_live": False,
            "failure_reasons": experiment.failure_reasons,
        }
        commentary = self.brain.report_commentary(
            campaign_id=campaign.campaign_id,
            facts=facts,
        )
        report_parts = [
            f"# {campaign.title}",
            "",
            f"Campaign: `{campaign.campaign_id}`",
            f"Dataset: `{campaign.dataset_version_id}`",
            f"Regime: `{regime.regime.value}` ({regime.confidence:.1%})",
            f"Hypothesis: `{campaign.hypothesis_id}`",
            f"Strategy: `{experiment.strategy_name}`",
            "Locked parameters:",
            "```json",
            json.dumps(
                experiment.parameters,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            "```",
            f"Trial number including failed attempts: {experiment.trial_number}",
            f"Quant Score: **{experiment.quant_score.total:.1f}/100**",
            f"Aegis shadow approval: **{bool(risk and risk.approved_for_shadow)}**",
            "Paper approval: **False**",
            "Live approval: **False**",
            "",
            "## Failure reasons",
            failure_rows,
            "",
        ]

        if commentary is not None:
            report_parts.extend(
                (
                    "## Optional qualitative commentary (non-authoritative)",
                    "",
                    commentary,
                    "",
                    "> This text cannot change any metric, gate, size, or approval.",
                    "",
                )
            )

        report_parts.extend(
            (
                "> This is research evidence from a Demo/local environment, not financial advice.",
                "",
            )
        )
        report = "\n".join(report_parts)
        _atomic_write(report_path, report)
        artifacts = {**campaign.artifacts, "report": str(report_path)}

        if commentary is not None:
            artifacts["echo_commentary"] = commentary

        self.store.save_campaign(
            campaign.model_copy(
                update={
                    "artifacts": artifacts,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        return f"Echo published the factual report to {report_path}."

    def _live_bars(self, campaign: ResearchCampaignRecord) -> tuple[MarketBar, ...]:
        return self.monitor.gateway.recent_bars(
            campaign.pair,
            campaign.timeframe,
            count=self.config.lookback_bars,
        )

    def _frozen_bars(self, campaign: ResearchCampaignRecord) -> tuple[MarketBar, ...]:
        path_text = campaign.artifacts.get("dataset_snapshot")

        if path_text is None:
            refreshed = self.store.campaign_for_source(campaign.source_bar_key)
            path_text = refreshed.artifacts.get("dataset_snapshot") if refreshed else None

        if path_text is None:
            raise RuntimeError("Frozen dataset snapshot is missing.")

        payload = json.loads(Path(path_text).read_text(encoding="utf-8"))

        if not isinstance(payload, list):
            raise TypeError("Frozen dataset snapshot has an invalid structure.")

        return tuple(MarketBar.model_validate(row) for row in payload)

    def _campaign_directory(self, campaign: ResearchCampaignRecord) -> Path:
        path = self.config.artifact_root / campaign.campaign_id
        path.mkdir(parents=True, exist_ok=True)
        return path


    def _regime_robustness(
        self,
        bars: Sequence[MarketBar],
        strategy_name: StrategyName,
        parameters: dict[str, int | float | str],
    ) -> float:
        chunk_size = len(bars) // 3

        if chunk_size < 20:
            return 0.0

        positive = 0
        regimes: set[InstitutionalRegime] = set()
        evaluated = 0

        for index in range(3):
            start = index * chunk_size
            end = len(bars) if index == 2 else (index + 1) * chunk_size
            chunk = tuple(bars[start:end])

            if len(chunk) < 20:
                continue

            result = run_backtest(chunk, build_strategy(strategy_name, parameters))
            report = self.data_engine.inspect(chunk, source="frozen_regime_slice")
            assessment = self.regime_engine.assess(chunk, report)
            regimes.add(assessment.regime)
            positive += result.metrics.net_profit > 0
            evaluated += 1

        if evaluated == 0:
            return 0.0

        diversity_factor = min(1.0, len(regimes) / 2.0)
        return positive / evaluated * diversity_factor


def _hypothesis(
    hypothesis_id: str,
    campaign: ResearchCampaignRecord,
    strategy_name: StrategyName,
    parameters: dict[str, int | float | str],
    regime: InstitutionalRegimeAssessment,
) -> HypothesisRecord:
    rationale = {
        "time_series_momentum": (
            "Slow information diffusion can create persistent directional returns."
        ),
        "kalman_adaptive_trend": (
            "A latent state estimate can separate persistent slope from observation noise."
        ),
        "multi_horizon_vol_trend": (
            "Trend signals that agree across horizons may survive volatility scaling."
        ),
        "donchian_breakout": (
            "New range extremes can reflect persistent repricing rather than a one-bar shock."
        ),
        "kalman_mean_reversion": "Temporary deviations from a latent local fair value may decay.",
        "variance_ratio_regime_switch": (
            "Return persistence changes sign across trend and reversion regimes."
        ),
        "zscore_mean_reversion": (
            "Large standardized deviations may reflect temporary inventory imbalance."
        ),
        "volatility_breakout": "Volatility compression can precede persistent price expansion.",
        "garman_klass_vol_breakout": (
            "OHLC range shocks may carry directional information after costs."
        ),
        "buy_and_hold": "A passive baseline is required before attributing value to active logic.",
    }[strategy_name]

    return HypothesisRecord(
        hypothesis_id=hypothesis_id,
        campaign_id=campaign.campaign_id,
        strategy_name=strategy_name,
        parameters=parameters,
        statement=(
            f"{strategy_name} should retain positive cost-adjusted out-of-sample expectancy "
            f"during {regime.regime.value} observations."
        ),
        economic_rationale=rationale,
        falsification_criteria=(
            "Out-of-sample net result is non-positive.",
            "Purged walk-forward pass fraction is below 60%.",
            "Fewer than 60% of neighboring parameter variants are profitable in-sample.",
            "Stressed transaction costs remove the edge.",
            "Quant Score is below the declared threshold.",
        ),
        compatible_regimes=(regime.regime.value,),
    )


def _research_stage_record(
    name: ResearchStageName,
    agent_key: str,
) -> ResearchStageRecord:
    contracts: dict[
        ResearchStageName,
        tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
    ] = {
        ResearchStageName.DATA_INTELLIGENCE: (
            ("MT5 completed-bar reader", "quality inspector", "SHA-256 dataset versioner"),
            ("completed OHLCV bars", "bid/ask spread"),
            ("immutable dataset snapshot", "quality report", "capability matrix"),
        ),
        ResearchStageName.REGIME_ANALYSIS: (
            (
                "pair-calibrated Baum-Welch HMM",
                "GMM volatility",
                "Bayesian change-point",
                "Kalman filter",
            ),
            ("frozen dataset version", "spread history"),
            ("probabilistic regime", "transition probability", "compatible families"),
        ),
        ResearchStageName.MACRO_CAPABILITY_AUDIT: (
            ("feed capability auditor",),
            ("regime evidence", "macro/cross-asset feed state"),
            ("available evidence list", "explicit missing-feed list"),
        ),
        ResearchStageName.HYPOTHESIS_DESIGN: (
            ("deterministic Thompson sampler", "evolution queue", "optional bounded Nova LLM"),
            ("regime assessment", "Bandit posterior", "recorded campaign history"),
            ("locked strategy parameters", "falsifiable hypothesis", "selection evidence"),
        ),
        ResearchStageName.BACKTEST_VALIDATION: (
            ("next-bar backtester", "purged walk-forward", "cost stress", "Quant Score"),
            ("locked hypothesis", "frozen data", "embargoed OOS holdout"),
            ("full trial record", "advanced metrics", "failure reasons"),
        ),
        ResearchStageName.QUANT_AUDIT: (
            ("leakage audit", "multiple-testing penalty", "PBO estimator"),
            ("experiment record", "trial count", "purge/embargo declaration"),
            ("bias audit", "overfitting evidence"),
        ),
        ResearchStageName.RISK_REVIEW: (
            ("Aegis hard gates", "size throttle", "global kill switch"),
            ("data quality", "OOS drawdown", "liquidity", "Quant Score"),
            ("shadow decision", "blockers", "size multiplier"),
        ),
        ResearchStageName.CHALLENGER_EVOLUTION: (
            ("candidate versioner", "Quant-Score Bandit updater", "genetic mutator/crossover"),
            ("audited experiment", "Aegis decision", "validated parent challengers"),
            ("challenger or rejection", "untested child proposal", "posterior update"),
        ),
        ResearchStageName.REPORTING: (
            ("factual report renderer", "agent hand-off journal"),
            ("campaign evidence chain", "failures", "risk decision"),
            ("Markdown campaign report", "voice-ready summary"),
        ),
    }
    tools, inputs, outputs = contracts[name]
    return ResearchStageRecord(
        name=name,
        agent_key=agent_key,
        tools_used=tools,
        input_contract=inputs,
        output_contract=outputs,
    )


def _source_bar_key(scan: MarketScanResult) -> str:
    return f"{scan.pair}|{scan.timeframe}|{scan.latest_bar_at.isoformat()}"


def _position_notional_usd(symbol: str, volume_lots: float, current_price: float) -> float:
    normalized = "".join(character for character in symbol.upper() if character.isalpha())[:6]
    base_notional = volume_lots * 100_000.0

    if normalized[:3] == "USD":
        return base_notional

    if normalized[3:6] == "USD":
        return base_notional * current_price

    return base_notional * current_price


def _candidate_scenario_returns(campaign: ResearchCampaignRecord) -> tuple[float, ...]:
    path_text = campaign.artifacts.get("experiment")

    if path_text is None:
        return ()

    payload = json.loads(Path(path_text).read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        return ()

    out_of_sample = payload.get("out_of_sample")

    if not isinstance(out_of_sample, dict):
        return ()

    raw_curve = out_of_sample.get("equity_curve")

    if not isinstance(raw_curve, list):
        return ()

    equity = [
        float(row["equity"])
        for row in raw_curve
        if isinstance(row, dict) and isinstance(row.get("equity"), int | float)
    ]

    return tuple(
        (current - previous) / previous
        for previous, current in pairwise(equity)
        if previous != 0
    )


def _metrics_payload(result: BacktestResult) -> dict[str, float | int]:
    return result.metrics.model_dump(mode="python")


def _cost_fraction(result: BacktestResult) -> float:
    costs = sum(trade.costs for trade in result.trades)
    gross = sum(abs(trade.gross_profit) for trade in result.trades)
    return costs / max(1e-12, gross)


def _strategy_name(value: str) -> StrategyName:
    from ai_quant_lab.strategies import normalize_strategy_name

    return normalize_strategy_name(value)


def _required(value: str | None, label: str) -> str:
    if value is None:
        raise RuntimeError(f"Campaign {label} is missing.")
    return value


def _short_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:18]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".temporary")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
