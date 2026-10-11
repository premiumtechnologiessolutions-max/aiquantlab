from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents import (
    ActivityJournal,
    ActivityType,
    AgentMessageBus,
    AgentTeam,
    AtlasCoordinator,
    TaskBoard,
    TaskPriority,
    create_default_agent_team,
)
from ai_quant_lab.risk import assert_safe_mode
from ai_quant_lab.runtime.persistence import SQLiteOperationalStore
from ai_quant_lab.runtime.scheduler import RuntimeScheduler, ScheduledJob, ScheduledJobSnapshot


class LabRuntimeConfig(BaseModel):
    """Safe local process configuration for the always-on research runtime."""

    model_config = ConfigDict(frozen=True)

    operational_database: Path = Path("data/operational/lab.sqlite3")
    market_data_root: Path = Path("data/processed")
    report_root: Path = Path("data/reports")
    mode: str = "research"
    tick_seconds: float = Field(default=5.0, gt=0, le=300)
    daily_planning_interval_seconds: float = Field(default=3_600.0, gt=0)
    work_interval_seconds: float = Field(default=60.0, gt=0)


class LabRuntime:
    """Persistent coordinator, scheduler, message bus, and truthful work journal."""

    def __init__(
        self,
        config: LabRuntimeConfig | None = None,
    ) -> None:
        self.config = config or LabRuntimeConfig()
        assert_safe_mode(self.config.mode)
        self.store = SQLiteOperationalStore(self.config.operational_database)
        self.journal = ActivityJournal(
            events=self.store.load_events(),
            persist=self.store.append_event,
        )

        self.task_board = TaskBoard()
        self.task_board.restore_tasks(self.store.load_tasks())
        self.task_board.add_listener(self.store)
        self.task_board.add_listener(self.journal)

        self.message_bus = AgentMessageBus(
            messages=self.store.load_messages(),
            listeners=(self.store, self.journal),
        )
        self.team: AgentTeam = create_default_agent_team(self.task_board)
        self.coordinator = AtlasCoordinator(self.team)
        self.scheduler = RuntimeScheduler()
        self._started = False
        self._register_default_jobs()

    def start(self) -> None:
        """Start the runtime and immediately plan any missing daily work."""

        if self._started:
            return

        self._started = True
        self.journal.record(
            event_type=ActivityType.RUNTIME_STARTED,
            actor_key="atlas",
            message="AI Quant Lab runtime started in safe research mode.",
        )
        self.store.save_heartbeat("lab_runtime", status="healthy")
        self.ensure_daily_work()

    def stop(self) -> None:
        """Record a controlled shutdown without deleting unfinished work."""

        if not self._started:
            return

        self.journal.record(
            event_type=ActivityType.RUNTIME_STOPPED,
            actor_key="atlas",
            message="AI Quant Lab runtime stopped safely; task state was preserved.",
        )
        self.store.save_heartbeat("lab_runtime", status="stopped")
        self._started = False

    def run_once(
        self,
        now: datetime | None = None,
    ) -> tuple[ScheduledJobSnapshot, ...]:
        """Execute one bounded scheduler tick and update liveness."""

        if not self._started:
            self.start()

        resolved_now = now or datetime.now(UTC)
        self.store.save_heartbeat(
            "lab_runtime",
            status="healthy",
            observed_at=resolved_now,
        )

        return self.scheduler.run_due(resolved_now)

    def run_forever(self, stop_event: Event | None = None) -> None:
        """Run scheduled work until an external stop event is set."""

        resolved_stop_event = stop_event or Event()
        self.start()

        try:
            while not resolved_stop_event.is_set():
                self.run_once()
                resolved_stop_event.wait(self.config.tick_seconds)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def ensure_daily_work(
        self,
        day: datetime | None = None,
    ) -> tuple[str, ...]:
        """Create idempotent proactive work items for one UTC calendar day."""

        resolved_day = (day or datetime.now(UTC)).date()
        date_key = resolved_day.strftime("%Y%m%d")
        planned: list[str] = []

        work_items = (
            (
                "vega",
                "daily_market_data_check",
                "تدقيق تحديث وجودة بيانات السوق اليومية",
                TaskPriority.CRITICAL,
            ),
            (
                "iris",
                "daily_regime_review",
                "مراجعة حالات السوق والتغيّرات المحتملة",
                TaskPriority.HIGH,
            ),
            (
                "nova",
                "daily_strategy_research",
                "مراجعة Research Backlog واقتراح فرضية قابلة للاختبار",
                TaskPriority.NORMAL,
            ),
            (
                "sentinel",
                "daily_validation_audit",
                "تدقيق التجارب والنتائج الجديدة بشكل مستقل",
                TaskPriority.HIGH,
            ),
            (
                "echo",
                "daily_team_report",
                "إعداد تقرير يومي من سجل العمل الحقيقي",
                TaskPriority.NORMAL,
            ),
        )

        for agent_key, prefix, title, priority in work_items:
            task_id = f"{prefix}_{date_key}"

            try:
                self.task_board.get_task(task_id)
            except KeyError:
                created = self.task_board.create_task(
                    task_id=task_id,
                    title=title,
                    description=(
                        "مهمة دورية أنشأها LabRuntime تلقائيًا؛ لا تنفذ تداولًا حيًا."
                    ),
                    priority=priority,
                    required_agent_key=agent_key,
                    tags=("daily", "automatic", "research_only"),
                )
                self.task_board.assign_task(created.task_id, agent_key)
                planned.append(created.task_id)

        return tuple(planned)

    def execute_ready_tasks(self) -> tuple[str, ...]:
        """Run bounded deterministic handlers for newly assigned daily work."""

        completed: list[str] = []

        for task in self.task_board.active_tasks():
            if task.status.value != "assigned" or "automatic" not in task.tags:
                continue

            agent_key = task.assigned_agent_key

            if agent_key is None:
                continue

            agent = self.team.get_agent(agent_key)
            agent.start_assigned_task(task.task_id)

            if task.task_id.startswith("daily_market_data_check_"):
                result = self._inspect_market_data()
            elif task.task_id.startswith("daily_regime_review_"):
                result = self._review_regime_inputs()
            elif task.task_id.startswith("daily_strategy_research_"):
                result = self._review_research_backlog()
            elif task.task_id.startswith("daily_validation_audit_"):
                result = self._audit_experiment_reports()
            elif task.task_id.startswith("daily_team_report_"):
                result = self._write_daily_report()
            else:
                agent.wait(message="No deterministic handler is registered for this task.")
                continue

            agent.complete_task(message=result)
            completed.append(task.task_id)

        return tuple(completed)

    def _register_default_jobs(self) -> None:
        """Register idempotent built-in maintenance jobs."""

        self.scheduler.register(
            ScheduledJob(
                job_key="daily_work_planner",
                interval_seconds=self.config.daily_planning_interval_seconds,
                callback=self.ensure_daily_work,
            )
        )
        self.scheduler.register(
            ScheduledJob(
                job_key="deterministic_work_executor",
                interval_seconds=self.config.work_interval_seconds,
                callback=self.execute_ready_tasks,
            )
        )

    def _inspect_market_data(self) -> str:
        """Inspect actual canonical manifests without changing market history."""

        manifests = tuple(self.config.market_data_root.glob("*/*/manifest.json"))
        valid = 0
        invalid = 0

        for path in manifests:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                required = {"pair", "timeframe", "bar_count", "sha256"}

                if required <= payload.keys():
                    valid += 1
                else:
                    invalid += 1
            except (OSError, json.JSONDecodeError):
                invalid += 1

        return f"Inspected {len(manifests)} dataset manifests: {valid} valid, {invalid} invalid."

    def _review_regime_inputs(self) -> str:
        """Report how many datasets are currently ready for regime detection."""

        dataset_count = sum(
            1
            for _ in self.config.market_data_root.glob("*/*/bars.parquet")
        )

        return (
            f"Found {dataset_count} canonical datasets available for regime analysis; "
            "no market state was invented."
        )

    def _review_research_backlog(self) -> str:
        """Count real pending tasks that can become future research work."""

        pending = self.task_board.pending_tasks()

        return f"Reviewed the task board and found {len(pending)} pending research items."

    def _audit_experiment_reports(self) -> str:
        """Count persisted experiment reports available for independent audit."""

        experiment_root = self.config.report_root.parent / "experiments"
        reports = tuple(experiment_root.glob("*/report.json"))
        invalid = 0

        for path in reports:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))

                if "validation" not in payload or "backtest" not in payload:
                    invalid += 1
            except (OSError, json.JSONDecodeError):
                invalid += 1

        return f"Audited {len(reports)} experiment reports; {invalid} were structurally invalid."

    def _write_daily_report(self) -> str:
        """Write a UTF-8 daily report from the append-only activity journal."""

        day = datetime.now(UTC).date()
        self.config.report_root.mkdir(parents=True, exist_ok=True)
        path = self.config.report_root / f"{day.isoformat()}.md"
        summary = self.journal.daily_summary(day)
        temporary_path = path.with_suffix(".temporary.md")
        temporary_path.write_text(
            f"# AI Quant Lab Daily Report — {day.isoformat()}\n\n{summary}\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

        return f"Wrote the real daily activity report to {path}."


def run_runtime(
    database_path: str | Path = "data/operational/lab.sqlite3",
) -> None:
    """Convenience entry point for a persistent foreground Windows process."""

    runtime = LabRuntime(
        LabRuntimeConfig(operational_database=Path(database_path)),
    )
    runtime.run_forever()
