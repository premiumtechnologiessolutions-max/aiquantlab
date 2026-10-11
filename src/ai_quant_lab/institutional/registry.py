from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.institutional.data_intelligence import DatasetQualityReport
from ai_quant_lab.institutional.regime_engine import InstitutionalRegimeAssessment
from ai_quant_lab.institutional.scoring import (
    AdvancedPerformanceMetrics,
    QuantScore,
    QuantScoreEvidence,
)
from ai_quant_lab.institutional.selection import (
    BanditArmState,
    BanditSelection,
    BanditUpdate,
    thompson_select,
    update_arm,
)
from ai_quant_lab.strategies import StrategyName


class CampaignStatus(StrEnum):
    """Durable lifecycle of an autonomous research campaign."""

    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ResearchStageStatus(StrEnum):
    """Durable lifecycle of one evidence-producing campaign stage."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ResearchStageName(StrEnum):
    """Ordered hand-offs used by the institutional research loop."""

    DATA_INTELLIGENCE = "data_intelligence"
    REGIME_ANALYSIS = "regime_analysis"
    MACRO_CAPABILITY_AUDIT = "macro_capability_audit"
    HYPOTHESIS_DESIGN = "hypothesis_design"
    BACKTEST_VALIDATION = "backtest_validation"
    QUANT_AUDIT = "quant_audit"
    RISK_REVIEW = "risk_review"
    CHALLENGER_EVOLUTION = "challenger_evolution"
    REPORTING = "reporting"


class EvolutionProposalStatus(StrEnum):
    """Queue state for a genetic child before independent validation."""

    PENDING = "pending"
    CONSUMED = "consumed"


class StrategyResearchStatus(StrEnum):
    """Research lifecycle separated from broker execution permissions."""

    IDEA = "idea"
    RESEARCHING = "researching"
    REJECTED = "rejected"
    VALIDATED = "validated"
    PAPER_TRADING = "paper_trading"
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    DEGRADED = "degraded"
    RETIRED = "retired"


class ResearchControl(BaseModel):
    """Persistent operator controls; emergency stop always overrides the loop."""

    model_config = ConfigDict(frozen=True)

    loop_enabled: bool = True
    emergency_stop: bool = False
    reason: str = "Continuous research enabled."
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchStageRecord(BaseModel):
    """One stage linked to a real task-board row and its evidence summary."""

    model_config = ConfigDict(frozen=True)

    name: ResearchStageName
    agent_key: str
    task_id: str | None = None
    status: ResearchStageStatus = ResearchStageStatus.PENDING
    progress_percent: float = Field(default=0.0, ge=0, le=100)
    tools_used: tuple[str, ...] = ()
    input_contract: tuple[str, ...] = ()
    output_contract: tuple[str, ...] = ()
    produced_outputs: tuple[str, ...] = ()
    summary: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ResearchCampaignRecord(BaseModel):
    """Central, restart-safe record of one full hypothesis lifecycle."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str
    source_bar_key: str
    pair: ForexPair
    timeframe: Timeframe
    latest_bar_at: datetime
    title: str
    status: CampaignStatus
    root_task_id: str
    current_stage_index: int = Field(default=0, ge=0)
    stages: tuple[ResearchStageRecord, ...]
    dataset_version_id: str | None = None
    regime_assessment_id: str | None = None
    hypothesis_id: str | None = None
    experiment_id: str | None = None
    strategy_name: str | None = None
    strategy_parameters: dict[str, int | float | str] = Field(default_factory=dict)
    evolution_proposal_id: str | None = None
    candidate_version_id: str | None = None
    quant_score: float | None = Field(default=None, ge=0, le=100)
    risk_decision: str | None = None
    summary: str | None = None
    failure_reasons: tuple[str, ...] = ()
    artifacts: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HypothesisRecord(BaseModel):
    """Falsifiable economic or behavioral claim proposed before testing."""

    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    campaign_id: str
    proposed_by: str = "nova"
    strategy_name: str
    parameters: dict[str, int | float | str] = Field(default_factory=dict)
    statement: str
    economic_rationale: str
    falsification_criteria: tuple[str, ...]
    compatible_regimes: tuple[str, ...]
    parameters_locked_before_test: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InstitutionalExperimentRecord(BaseModel):
    """Every attempted test, including failures, for multiple-testing control."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    campaign_id: str
    hypothesis_id: str
    dataset_version_id: str
    strategy_name: str
    parameters: dict[str, int | float | str]
    trial_number: int = Field(ge=1)
    in_sample_metrics: dict[str, float | int]
    out_of_sample_metrics: dict[str, float | int]
    stressed_metrics: dict[str, float | int]
    advanced_metrics: AdvancedPerformanceMetrics
    score_evidence: QuantScoreEvidence
    quant_score: QuantScore
    purge_bars: int = Field(ge=0)
    embargo_bars: int = Field(ge=0)
    attempted_after_viewing_test_data: bool = False
    failure_reasons: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RiskDecisionRecord(BaseModel):
    """Aegis decision with hard blockers and zero implicit live authority."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    campaign_id: str
    approved_for_shadow: bool
    approved_for_paper: Literal[False] = False
    approved_for_live: Literal[False] = False
    size_multiplier: float = Field(ge=0, le=1)
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    kill_switch_triggered: bool
    portfolio_gross_leverage: float = Field(default=0.0, ge=0)
    portfolio_cvar_95_fraction: float = Field(default=0.0, le=0)
    maximum_currency_exposure_fraction: float = Field(default=0.0, ge=0)
    correlated_bet_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrategyCandidateRecord(BaseModel):
    """Champion–challenger registry entry that never auto-promotes to paper/live."""

    model_config = ConfigDict(frozen=True)

    version_id: str
    campaign_id: str
    parent_version_id: str | None = None
    pair: ForexPair | None = None
    timeframe: Timeframe | None = None
    strategy_name: str
    parameters: dict[str, int | float | str]
    status: StrategyResearchStatus
    regime_specialization: str
    quant_score: float = Field(ge=0, le=100)
    reason: str
    human_approval_required: Literal[True] = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrategyEvolutionProposalRecord(BaseModel):
    """Genetic child queued as an idea until the full pipeline validates it."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    pair: ForexPair
    timeframe: Timeframe
    regime: str
    strategy_name: str
    parameters: dict[str, int | float | str]
    parent_version_ids: tuple[str, ...]
    generation: int = Field(default=1, ge=1)
    status: EvolutionProposalStatus = EvolutionProposalStatus.PENDING
    consumed_by_campaign_id: str | None = None
    human_approval_required: Literal[True] = True
    live_trading_authorized: Literal[False] = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    consumed_at: datetime | None = None


class InstitutionalResearchStore:
    """Append-preserving SQLite registry for campaigns, trials, and controls."""

    def __init__(self, path: str | Path = "data/institutional/research.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def control(self) -> ResearchControl:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM research_control WHERE control_key = 'main'"
            ).fetchone()

        return ResearchControl.model_validate_json(row[0]) if row else ResearchControl()

    def set_control(
        self,
        *,
        loop_enabled: bool | None = None,
        emergency_stop: bool | None = None,
        reason: str,
    ) -> ResearchControl:
        current = self.control()
        updated = current.model_copy(
            update={
                "loop_enabled": current.loop_enabled if loop_enabled is None else loop_enabled,
                "emergency_stop": (
                    current.emergency_stop if emergency_stop is None else emergency_stop
                ),
                "reason": reason.strip() or current.reason,
                "updated_at": datetime.now(UTC),
            }
        )

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_control(control_key, payload, updated_at)
                VALUES ('main', ?, ?)
                ON CONFLICT(control_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (updated.model_dump_json(), updated.updated_at.isoformat()),
            )

        return updated

    def save_campaign(self, campaign: ResearchCampaignRecord) -> ResearchCampaignRecord:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO research_campaigns(
                    campaign_id, source_bar_key, status, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    status = excluded.status,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    campaign.campaign_id,
                    campaign.source_bar_key,
                    campaign.status.value,
                    campaign.model_dump_json(),
                    campaign.created_at.isoformat(),
                    campaign.updated_at.isoformat(),
                ),
            )

        return campaign

    def campaign_for_source(self, source_bar_key: str) -> ResearchCampaignRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM research_campaigns WHERE source_bar_key = ?",
                (source_bar_key,),
            ).fetchone()

        return ResearchCampaignRecord.model_validate_json(row[0]) if row else None

    def active_campaign(self) -> ResearchCampaignRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload FROM research_campaigns
                WHERE status IN ('active', 'queued', 'paused')
                ORDER BY created_at, campaign_id LIMIT 1
                """
            ).fetchone()

        return ResearchCampaignRecord.model_validate_json(row[0]) if row else None

    def recent_campaigns(self, limit: int = 20) -> tuple[ResearchCampaignRecord, ...]:
        if limit < 1 or limit > 200:
            raise ValueError("Campaign limit must be between one and two hundred.")

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM research_campaigns "
                "ORDER BY created_at DESC, campaign_id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return tuple(ResearchCampaignRecord.model_validate_json(row[0]) for row in rows)

    def record_dataset(self, report: DatasetQualityReport) -> DatasetQualityReport:
        self._insert_immutable("datasets", "dataset_version_id", report.dataset_version_id, report)
        return report

    def record_regime(
        self,
        assessment: InstitutionalRegimeAssessment,
    ) -> InstitutionalRegimeAssessment:
        self._insert_immutable(
            "regime_assessments",
            "assessment_id",
            assessment.assessment_id,
            assessment,
        )
        return assessment

    def record_hypothesis(self, hypothesis: HypothesisRecord) -> HypothesisRecord:
        self._insert_immutable(
            "hypotheses",
            "hypothesis_id",
            hypothesis.hypothesis_id,
            hypothesis,
        )
        return hypothesis

    def record_experiment(
        self,
        experiment: InstitutionalExperimentRecord,
    ) -> InstitutionalExperimentRecord:
        self._insert_immutable(
            "institutional_experiments",
            "experiment_id",
            experiment.experiment_id,
            experiment,
        )
        return experiment

    def record_risk_decision(self, decision: RiskDecisionRecord) -> RiskDecisionRecord:
        self._insert_immutable(
            "risk_decisions",
            "decision_id",
            decision.decision_id,
            decision,
        )
        return decision

    def record_candidate(
        self,
        candidate: StrategyCandidateRecord,
    ) -> StrategyCandidateRecord:
        self._insert_immutable(
            "strategy_candidates",
            "version_id",
            candidate.version_id,
            candidate,
        )
        return candidate

    def select_bandit_arm(
        self,
        *,
        campaign_id: str,
        pair: ForexPair,
        timeframe: Timeframe,
        regime: str,
        strategy_names: tuple[StrategyName, ...],
    ) -> BanditSelection:
        """Select and persist exactly one deterministic Thompson draw per campaign."""

        with self._connection() as connection:
            existing = connection.execute(
                "SELECT payload FROM bandit_selections WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()

            if existing is not None:
                stored = BanditSelection.model_validate_json(existing[0])

                if (
                    stored.pair != pair
                    or stored.timeframe != timeframe
                    or stored.regime.value != regime
                    or stored.strategy_name not in strategy_names
                ):
                    raise ValueError(
                        f"Campaign '{campaign_id}' already has a different Bandit selection."
                    )

                return stored

            arms: list[BanditArmState] = []

            for strategy_name in strategy_names:
                key = _bandit_arm_key(pair, timeframe, regime, strategy_name)
                row = connection.execute(
                    "SELECT payload FROM strategy_bandit_arms WHERE arm_key = ?",
                    (key,),
                ).fetchone()
                arm = (
                    BanditArmState.model_validate_json(row[0])
                    if row is not None
                    else BanditArmState(
                        pair=pair,
                        timeframe=timeframe,
                        regime=regime,
                        strategy_name=strategy_name,
                    )
                )
                arms.append(arm)

            selection = thompson_select(tuple(arms), campaign_id=campaign_id)

            for arm in arms:
                updated = (
                    arm.model_copy(
                        update={
                            "selections": arm.selections + 1,
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    if arm.strategy_name == selection.strategy_name
                    else arm
                )
                key = _bandit_arm_key(pair, timeframe, regime, arm.strategy_name)
                connection.execute(
                    """
                    INSERT INTO strategy_bandit_arms(arm_key, payload, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(arm_key) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (key, updated.model_dump_json(), updated.updated_at.isoformat()),
                )

            connection.execute(
                "INSERT INTO bandit_selections(campaign_id, payload, created_at) VALUES (?, ?, ?)",
                (campaign_id, selection.model_dump_json(), selection.selected_at.isoformat()),
            )

        return selection

    def apply_bandit_update(self, update: BanditUpdate) -> BanditUpdate:
        """Apply a campaign Quant Score to one arm once, preserving replay safety."""

        with self._connection() as connection:
            selection_row = connection.execute(
                "SELECT payload FROM bandit_selections WHERE campaign_id = ?",
                (update.campaign_id,),
            ).fetchone()

            if selection_row is None:
                raise ValueError(
                    f"Campaign '{update.campaign_id}' has no recorded Bandit selection."
                )

            selection = BanditSelection.model_validate_json(selection_row[0])

            if (
                selection.pair != update.pair
                or selection.timeframe != update.timeframe
                or selection.regime is not update.regime
                or selection.strategy_name != update.strategy_name
            ):
                raise ValueError(
                    f"Campaign '{update.campaign_id}' outcome does not match its selection."
                )

            existing = connection.execute(
                "SELECT payload FROM bandit_updates WHERE campaign_id = ?",
                (update.campaign_id,),
            ).fetchone()

            if existing is not None:
                stored = BanditUpdate.model_validate_json(existing[0])

                comparable_stored = stored.model_dump(exclude={"created_at"})
                comparable_update = update.model_dump(exclude={"created_at"})

                if comparable_stored != comparable_update:
                    raise ValueError(
                        f"Campaign '{update.campaign_id}' already has another bandit outcome."
                    )

                return stored

            key = _bandit_arm_key(
                update.pair,
                update.timeframe,
                update.regime.value,
                update.strategy_name,
            )
            row = connection.execute(
                "SELECT payload FROM strategy_bandit_arms WHERE arm_key = ?",
                (key,),
            ).fetchone()
            arm = (
                BanditArmState.model_validate_json(row[0])
                if row is not None
                else BanditArmState(
                    pair=update.pair,
                    timeframe=update.timeframe,
                    regime=update.regime,
                    strategy_name=update.strategy_name,
                )
            )
            updated_arm = update_arm(arm, quant_score=update.quant_score)
            connection.execute(
                """
                INSERT INTO strategy_bandit_arms(arm_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(arm_key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (key, updated_arm.model_dump_json(), updated_arm.updated_at.isoformat()),
            )
            connection.execute(
                "INSERT INTO bandit_updates(campaign_id, payload, created_at) VALUES (?, ?, ?)",
                (update.campaign_id, update.model_dump_json(), update.created_at.isoformat()),
            )

        return update

    def bandit_arms(
        self,
        *,
        pair: ForexPair,
        timeframe: Timeframe,
        regime: str,
    ) -> tuple[BanditArmState, ...]:
        """Return posterior state for one exact pair/timeframe/regime context."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM strategy_bandit_arms "
                "WHERE json_extract(payload, '$.pair') = ? "
                "AND json_extract(payload, '$.timeframe') = ? "
                "AND json_extract(payload, '$.regime') = ? "
                "ORDER BY json_extract(payload, '$.strategy_name')",
                (pair, timeframe, regime),
            ).fetchall()

        return tuple(BanditArmState.model_validate_json(row[0]) for row in rows)

    def record_evolution_proposal(
        self,
        proposal: StrategyEvolutionProposalRecord,
    ) -> StrategyEvolutionProposalRecord:
        self._insert_immutable(
            "evolution_proposals",
            "proposal_id",
            proposal.proposal_id,
            proposal,
        )
        return proposal

    def evolution_proposal(self, proposal_id: str) -> StrategyEvolutionProposalRecord:
        payload = self._one_payload("evolution_proposals", "proposal_id", proposal_id)
        return StrategyEvolutionProposalRecord.model_validate_json(payload)

    def pending_evolution_proposal(
        self,
        *,
        pair: ForexPair,
        timeframe: Timeframe,
        regime: str,
        strategy_name: str,
    ) -> StrategyEvolutionProposalRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM evolution_proposals "
                "WHERE json_extract(payload, '$.pair') = ? "
                "AND json_extract(payload, '$.timeframe') = ? "
                "AND json_extract(payload, '$.regime') = ? "
                "AND json_extract(payload, '$.strategy_name') = ? "
                "AND json_extract(payload, '$.status') = 'pending' "
                "ORDER BY created_at, proposal_id LIMIT 1",
                (pair, timeframe, regime, strategy_name),
            ).fetchone()

        return StrategyEvolutionProposalRecord.model_validate_json(row[0]) if row else None

    def consume_evolution_proposal(
        self,
        proposal_id: str,
        *,
        campaign_id: str,
    ) -> StrategyEvolutionProposalRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM evolution_proposals WHERE proposal_id = ?",
                (proposal_id,),
            ).fetchone()

            if row is None:
                raise KeyError(f"Unknown evolution proposal '{proposal_id}'.")

            proposal = StrategyEvolutionProposalRecord.model_validate_json(row[0])

            if proposal.status is EvolutionProposalStatus.CONSUMED:
                if proposal.consumed_by_campaign_id != campaign_id:
                    raise ValueError(f"Evolution proposal '{proposal_id}' is already consumed.")
                return proposal

            updated = proposal.model_copy(
                update={
                    "status": EvolutionProposalStatus.CONSUMED,
                    "consumed_by_campaign_id": campaign_id,
                    "consumed_at": datetime.now(UTC),
                }
            )
            connection.execute(
                "UPDATE evolution_proposals SET payload = ? WHERE proposal_id = ?",
                (updated.model_dump_json(), proposal_id),
            )

        return updated

    def top_challengers(
        self,
        *,
        pair: ForexPair,
        timeframe: Timeframe,
        regime: str,
        strategy_name: str,
        limit: int = 2,
    ) -> tuple[StrategyCandidateRecord, ...]:
        if limit < 1 or limit > 20:
            raise ValueError("Challenger limit must be between one and twenty.")

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM strategy_candidates "
                "WHERE json_extract(payload, '$.status') = 'challenger' "
                "AND json_extract(payload, '$.pair') = ? "
                "AND json_extract(payload, '$.timeframe') = ? "
                "AND json_extract(payload, '$.regime_specialization') = ? "
                "AND json_extract(payload, '$.strategy_name') = ? "
                "ORDER BY CAST(json_extract(payload, '$.quant_score') AS REAL) DESC, created_at "
                "LIMIT ?",
                (pair, timeframe, regime, strategy_name, limit),
            ).fetchall()

        return tuple(StrategyCandidateRecord.model_validate_json(row[0]) for row in rows)

    def recent_hypotheses(self, limit: int = 12) -> tuple[HypothesisRecord, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("Hypothesis limit must be between one and one hundred.")

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM hypotheses ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return tuple(HypothesisRecord.model_validate_json(row[0]) for row in rows)

    def experiment(self, experiment_id: str) -> InstitutionalExperimentRecord:
        payload = self._one_payload(
            "institutional_experiments",
            "experiment_id",
            experiment_id,
        )
        return InstitutionalExperimentRecord.model_validate_json(payload)

    def hypothesis(self, hypothesis_id: str) -> HypothesisRecord:
        payload = self._one_payload("hypotheses", "hypothesis_id", hypothesis_id)
        return HypothesisRecord.model_validate_json(payload)

    def dataset(self, dataset_version_id: str) -> DatasetQualityReport:
        payload = self._one_payload("datasets", "dataset_version_id", dataset_version_id)
        return DatasetQualityReport.model_validate_json(payload)

    def regime(self, assessment_id: str) -> InstitutionalRegimeAssessment:
        payload = self._one_payload(
            "regime_assessments",
            "assessment_id",
            assessment_id,
        )
        return InstitutionalRegimeAssessment.model_validate_json(payload)

    def latest_risk_decision(self, campaign_id: str) -> RiskDecisionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM risk_decisions "
                "WHERE json_extract(payload, '$.campaign_id') = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()

        return RiskDecisionRecord.model_validate_json(row[0]) if row else None

    def trial_count(self, strategy_name: str | None = None) -> int:
        with self._connection() as connection:
            if strategy_name is None:
                row = connection.execute(
                    "SELECT COUNT(*) FROM institutional_experiments"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM institutional_experiments "
                    "WHERE json_extract(payload, '$.strategy_name') = ?",
                    (strategy_name,),
                ).fetchone()

        return int(row[0]) if row else 0

    def counts(self) -> dict[str, int]:
        tables = (
            "research_campaigns",
            "datasets",
            "regime_assessments",
            "hypotheses",
            "institutional_experiments",
            "risk_decisions",
            "strategy_candidates",
            "strategy_bandit_arms",
            "bandit_selections",
            "bandit_updates",
            "evolution_proposals",
        )
        counts: dict[str, int] = {}

        with self._connection() as connection:
            for table in tables:
                row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                counts[table] = int(row[0]) if row else 0

        return counts

    def _insert_immutable(
        self,
        table: str,
        id_column: str,
        identifier: str,
        payload: BaseModel,
    ) -> None:
        with self._connection() as connection:
            existing = connection.execute(
                f"SELECT payload FROM {table} WHERE {id_column} = ?",
                (identifier,),
            ).fetchone()

            if existing is not None:
                if existing[0] != payload.model_dump_json():
                    raise ValueError(f"Immutable record '{identifier}' already has other content.")
                return

            connection.execute(
                f"INSERT INTO {table}({id_column}, payload, created_at) VALUES (?, ?, ?)",
                (identifier, payload.model_dump_json(), datetime.now(UTC).isoformat()),
            )

    def _one_payload(self, table: str, id_column: str, identifier: str) -> str:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE {id_column} = ?",
                (identifier,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Record '{identifier}' does not exist in {table}.")

        return str(row[0])

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS research_control (
                    control_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS research_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    source_bar_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_version_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS regime_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS hypotheses (
                    hypothesis_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS institutional_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS risk_decisions (
                    decision_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS strategy_candidates (
                    version_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS strategy_bandit_arms (
                    arm_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bandit_selections (
                    campaign_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bandit_updates (
                    campaign_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evolution_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            row = connection.execute(
                "SELECT 1 FROM research_control WHERE control_key = 'main'"
            ).fetchone()

            if row is None:
                control = ResearchControl()
                connection.execute(
                    "INSERT INTO research_control(control_key, payload, updated_at) "
                    "VALUES ('main', ?, ?)",
                    (control.model_dump_json(), control.updated_at.isoformat()),
                )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path)

            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()


def _bandit_arm_key(
    pair: ForexPair,
    timeframe: Timeframe,
    regime: str,
    strategy_name: str,
) -> str:
    return f"{pair}|{timeframe}|{regime}|{strategy_name}"
