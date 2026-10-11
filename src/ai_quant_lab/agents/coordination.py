from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents.base import BaseAgent
from ai_quant_lab.agents.identifiers import normalize_identifier
from ai_quant_lab.agents.tasks import (
    AgentTask,
    TaskBoard,
    TaskPriority,
    TaskStatus,
)
from ai_quant_lab.agents.team import AgentTeam

DEFAULT_COORDINATOR_KEY = "atlas"


class AgentWorkload(BaseModel):
    """Immutable summary of the real work owned by one agent."""

    model_config = ConfigDict(frozen=True)

    agent_key: str
    agent_name: str

    active_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    cancelled_tasks: int = Field(ge=0)

    current_task_id: str | None = None
    current_task_title: str | None = None
    current_progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )

    @property
    def total_tasks(self) -> int:
        """Return every task ever assigned to this agent."""

        return (
            self.active_tasks
            + self.completed_tasks
            + self.failed_tasks
            + self.cancelled_tasks
        )

    @property
    def is_busy(self) -> bool:
        """Return whether the agent currently owns unfinished work."""

        return self.active_tasks > 0


class TeamProgress(BaseModel):
    """Immutable progress report computed from the shared task board."""

    model_config = ConfigDict(frozen=True)

    total_tasks: int = Field(ge=0)
    pending_tasks: int = Field(ge=0)
    active_tasks: int = Field(ge=0)
    completed_tasks: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    cancelled_tasks: int = Field(ge=0)

    progress_percent: float = Field(
        ge=0.0,
        le=100.0,
    )

    workloads: tuple[AgentWorkload, ...] = ()

    @property
    def busy_agents(self) -> tuple[AgentWorkload, ...]:
        """Return only the agents that currently own unfinished work."""

        return tuple(
            workload
            for workload in self.workloads
            if workload.is_busy
        )

    @property
    def idle_agents(self) -> tuple[AgentWorkload, ...]:
        """Return only the agents that currently own no unfinished work."""

        return tuple(
            workload
            for workload in self.workloads
            if not workload.is_busy
        )


class AtlasCoordinator:
    """Deterministic delegation API used by the Atlas coordinator agent.

    The coordinator never invents work state. It only creates, assigns, and
    reads rows on the shared team task board, and it refuses to delegate to
    an agent that is not registered in the team.
    """

    def __init__(
        self,
        team: AgentTeam,
        coordinator_key: str = DEFAULT_COORDINATOR_KEY,
    ) -> None:
        normalized_key = normalize_identifier(
            coordinator_key,
            field_name="Coordinator key",
        )

        if not team.has_agent(normalized_key):
            raise KeyError(
                f"Coordinator agent '{normalized_key}' is not registered.",
            )

        self._team = team
        self._coordinator_key = normalized_key

    @property
    def team(self) -> AgentTeam:
        """Return the team coordinated by this instance."""

        return self._team

    @property
    def task_board(self) -> TaskBoard:
        """Return the shared team task board."""

        return self._team.task_board

    @property
    def coordinator(self) -> BaseAgent:
        """Return the agent acting as coordinator."""

        return self._team.get_agent(self._coordinator_key)

    def delegate(
        self,
        *,
        agent_key: str,
        title: str,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        parent_task_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> AgentTask:
        """Create one task and assign it to a registered agent."""

        normalized_agent_key = self._require_registered_agent(agent_key)

        created = self.task_board.create_task(
            title=title,
            description=description,
            priority=priority,
            required_agent_key=normalized_agent_key,
            parent_task_id=parent_task_id,
            tags=tags,
        )

        return self.task_board.assign_task(
            created.task_id,
            normalized_agent_key,
        )

    def plan_task(
        self,
        *,
        title: str,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        required_agent_key: str | None = None,
        parent_task_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> AgentTask:
        """Create one unassigned backlog task for later dispatch."""

        normalized_agent_key = (
            self._require_registered_agent(required_agent_key)
            if required_agent_key is not None
            else None
        )

        return self.task_board.create_task(
            title=title,
            description=description,
            priority=priority,
            required_agent_key=normalized_agent_key,
            parent_task_id=parent_task_id,
            tags=tags,
        )

    def assign(
        self,
        task_id: str,
        agent_key: str,
    ) -> AgentTask:
        """Assign one existing pending task to a registered agent."""

        normalized_agent_key = self._require_registered_agent(agent_key)

        return self.task_board.assign_task(
            task_id,
            normalized_agent_key,
        )

    def reassign(
        self,
        task_id: str,
        agent_key: str,
    ) -> AgentTask:
        """Move one active task to a different registered agent."""

        normalized_agent_key = self._require_registered_agent(agent_key)

        return self.task_board.reassign_task(
            task_id,
            normalized_agent_key,
        )

    def dispatch_backlog(self) -> tuple[AgentTask, ...]:
        """Assign every backlog task that already names a registered agent."""

        dispatched: list[AgentTask] = []

        for task in self.task_board.pending_tasks():
            if task.required_agent_key is None:
                continue

            if not self._team.has_agent(task.required_agent_key):
                continue

            dispatched.append(
                self.task_board.assign_task(
                    task.task_id,
                    task.required_agent_key,
                )
            )

        return tuple(dispatched)

    def cancel(
        self,
        task_id: str,
    ) -> AgentTask:
        """Cancel one task and every unfinished subtask below it."""

        return self.task_board.cancel_task(task_id)

    def tasks_for_agent(
        self,
        agent_key: str,
    ) -> tuple[AgentTask, ...]:
        """Return every task assigned to one registered agent."""

        normalized_agent_key = self._require_registered_agent(agent_key)

        return self.task_board.tasks_for_agent(
            normalized_agent_key,
        )

    def active_tasks(self) -> tuple[AgentTask, ...]:
        """Return every unfinished team task, most urgent first."""

        return self.task_board.active_tasks()

    def unassigned_agents(self) -> tuple[BaseAgent, ...]:
        """Return every registered agent that currently owns no active task."""

        return tuple(
            agent
            for agent in self._team.all_agents()
            if agent.active_task() is None
        )

    def workload(
        self,
        agent_key: str,
    ) -> AgentWorkload:
        """Return the real workload summary of one registered agent."""

        normalized_agent_key = self._require_registered_agent(agent_key)
        agent = self._team.get_agent(normalized_agent_key)

        return _build_workload(agent)

    def progress_report(self) -> TeamProgress:
        """Return the current progress of the whole team."""

        tasks = self.task_board.all_tasks()

        counts = {
            status: sum(
                1
                for task in tasks
                if task.status is status
            )
            for status in TaskStatus
        }

        active_count = sum(
            1
            for task in tasks
            if task.is_active
        )

        measurable = [
            task
            for task in tasks
            if task.status is not TaskStatus.CANCELLED
        ]

        progress_percent = (
            sum(task.progress_percent for task in measurable) / len(measurable)
            if measurable
            else 0.0
        )

        return TeamProgress(
            total_tasks=len(tasks),
            pending_tasks=counts[TaskStatus.PENDING],
            active_tasks=active_count,
            completed_tasks=counts[TaskStatus.COMPLETED],
            failed_tasks=counts[TaskStatus.FAILED],
            cancelled_tasks=counts[TaskStatus.CANCELLED],
            progress_percent=round(progress_percent, 4),
            workloads=tuple(
                _build_workload(agent)
                for agent in self._team.all_agents()
            ),
        )

    def progress_reply(self) -> str:
        """Return a Lebanese-Arabic progress report built from real tasks."""

        report = self.progress_report()

        if report.total_tasks == 0:
            return (
                "Atlas: ما في أي مهمة مسجّلة على لوحة الفريق حاليًا."
            )

        lines = [
            (
                f"Atlas: مجموع المهام {report.total_tasks}، "
                f"شغّالة {report.active_tasks}، "
                f"بالانتظار {report.pending_tasks}، "
                f"مخلّصة {report.completed_tasks}، "
                f"فاشلة {report.failed_tasks}، "
                f"ملغاة {report.cancelled_tasks}. "
                f"التقدّم العام {report.progress_percent:.0f}%."
            ),
        ]

        busy = report.busy_agents

        if not busy:
            lines.append(
                "ما في أي Agent عم يشتغل على مهمة هلق.",
            )

            return "\n".join(lines)

        lines.extend(
            (
                f"- {workload.agent_name}: "
                f"{workload.active_tasks} مهمة شغّالة "
                f"({workload.current_task_title}, "
                f"{workload.current_progress_percent:.0f}%)"
            )
            for workload in busy
        )

        return "\n".join(lines)

    def active_tasks_reply(self) -> str:
        """Return a Lebanese-Arabic list of every unfinished team task."""

        tasks = self.active_tasks()

        if not tasks:
            return (
                "Atlas: ما في أي مهمة شغّالة عند الفريق هلق."
            )

        lines = [
            f"Atlas: في {len(tasks)} مهمة شغّالة:",
        ]

        lines.extend(
            (
                f"- [{task.task_id}] {task.title} "
                f"→ {task.assigned_agent_key} "
                f"({task.status.value}, {task.priority.value}, "
                f"{task.progress_percent:.0f}%)"
            )
            for task in tasks
        )

        return "\n".join(lines)

    def _require_registered_agent(
        self,
        agent_key: str,
    ) -> str:
        """Return a normalized agent key or reject an unknown agent."""

        normalized_agent_key = normalize_identifier(
            agent_key,
            field_name="Agent key",
        )

        if not self._team.has_agent(normalized_agent_key):
            raise KeyError(
                f"Agent '{normalized_agent_key}' is not registered "
                "in the team and cannot receive tasks.",
            )

        return normalized_agent_key


def _build_workload(
    agent: BaseAgent,
) -> AgentWorkload:
    """Build the workload summary of one agent from real board rows."""

    tasks = agent.assigned_tasks()
    current = agent.active_task()

    return AgentWorkload(
        agent_key=agent.identity.key,
        agent_name=agent.identity.name,
        active_tasks=sum(
            1
            for task in tasks
            if task.is_active
        ),
        completed_tasks=sum(
            1
            for task in tasks
            if task.status is TaskStatus.COMPLETED
        ),
        failed_tasks=sum(
            1
            for task in tasks
            if task.status is TaskStatus.FAILED
        ),
        cancelled_tasks=sum(
            1
            for task in tasks
            if task.status is TaskStatus.CANCELLED
        ),
        current_task_id=(
            current.task_id
            if current is not None
            else None
        ),
        current_task_title=(
            current.title
            if current is not None
            else None
        ),
        current_progress_percent=(
            current.progress_percent
            if current is not None
            else 0.0
        ),
    )
