from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from ai_quant_lab.agents.identifiers import normalize_identifier
from ai_quant_lab.agents.tasks import (
    AgentTask,
    TaskBoard,
    TaskPriority,
    TaskStatus,
)


class AgentState(StrEnum):
    """Operational state of one AI Quant Lab agent."""

    IDLE = "idle"
    ASSIGNED = "assigned"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
    STOPPED = "stopped"


_AGENT_STATE_BY_TASK_STATUS: dict[TaskStatus, AgentState] = {
    TaskStatus.PENDING: AgentState.IDLE,
    TaskStatus.ASSIGNED: AgentState.ASSIGNED,
    TaskStatus.RUNNING: AgentState.WORKING,
    TaskStatus.WAITING: AgentState.WAITING,
    TaskStatus.COMPLETED: AgentState.COMPLETED,
    TaskStatus.FAILED: AgentState.ERROR,
    TaskStatus.CANCELLED: AgentState.CANCELLED,
}

_DEFAULT_NOTE_BY_TASK_STATUS: dict[TaskStatus, str] = {
    TaskStatus.PENDING: "المهمة بعدها بانتظار التوزيع.",
    TaskStatus.ASSIGNED: "لسا ما بلّشت فيها.",
    TaskStatus.RUNNING: "المهمة بعدها قيد التنفيذ.",
    TaskStatus.WAITING: "ناطر معلومات إضافية.",
    TaskStatus.COMPLETED: "المهمة خلصت بنجاح.",
    TaskStatus.FAILED: "المهمة وقفت بسبب خطأ.",
    TaskStatus.CANCELLED: "المهمة انلغت.",
}

IDLE_AGENT_MESSAGE = "أنا حاضر وجاهز."
DEFAULT_STOP_MESSAGE = "تم إيقافي بأمان."


class AgentIdentity(BaseModel):
    """Permanent identity and role of one named agent."""

    model_config = ConfigDict(frozen=True)

    key: str
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    wake_names: tuple[str, ...] = ()

    @field_validator("key")
    @classmethod
    def normalize_key(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate the internal agent key."""

        return normalize_identifier(
            value,
            field_name="Agent key",
        )

    @field_validator("name", "role")
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
    ) -> str:
        """Remove surrounding spaces from required text."""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Agent name and role cannot be empty.",
            )

        return normalized

    @field_validator("wake_names")
    @classmethod
    def normalize_wake_names(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Normalize wake names and remove duplicates."""

        normalized_names: list[str] = []
        known_names: set[str] = set()

        for value in values:
            normalized = value.strip()

            if not normalized:
                raise ValueError(
                    "Agent wake names cannot be empty.",
                )

            comparison_key = normalized.casefold()

            if comparison_key in known_names:
                continue

            known_names.add(comparison_key)
            normalized_names.append(normalized)

        return tuple(normalized_names)


class AgentSnapshot(BaseModel):
    """Immutable current status of one agent."""

    model_config = ConfigDict(frozen=True)

    identity: AgentIdentity
    state: AgentState

    message: str = Field(min_length=1)
    current_task: str | None = None
    current_task_id: str | None = None
    active_task_count: int = Field(default=0, ge=0)
    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @field_validator("message")
    @classmethod
    def normalize_message(
        cls,
        value: str,
    ) -> str:
        """Normalize the agent status message."""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Agent status message cannot be empty.",
            )

        return normalized

    @field_validator("current_task")
    @classmethod
    def normalize_current_task(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize an optional task description."""

        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            return None

        return normalized

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone information and normalize to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Agent status timestamps must include timezone information.",
            )

        return value.astimezone(UTC)


class BaseAgent:
    """Named agent whose reported status is derived from real tasks.

    Every agent is backed by a :class:`TaskBoard`. A standalone agent owns a
    private board, while an agent registered inside an ``AgentTeam`` shares the
    team board. All status views are computed from board rows, so the agent
    never becomes a second source of truth about its own work.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        task_board: TaskBoard | None = None,
    ) -> None:
        self._identity = identity
        self._lock = RLock()
        self._board = (
            task_board
            if task_board is not None
            else TaskBoard()
        )

        self._stopped = False
        self._stop_note: str | None = None
        self._acknowledged_task_ids: set[str] = set()
        self._local_changed_at = datetime.now(UTC)

    @property
    def identity(self) -> AgentIdentity:
        """Return the permanent identity of the agent."""

        return self._identity

    @property
    def task_board(self) -> TaskBoard:
        """Return the task board that holds the work of this agent."""

        with self._lock:
            return self._board

    def bind_task_board(
        self,
        task_board: TaskBoard,
    ) -> None:
        """Attach the agent to a shared task board before it owns work."""

        current_board = self.task_board

        if task_board is current_board:
            return

        if current_board.tasks_for_agent(self._identity.key):
            raise RuntimeError(
                f"Agent '{self._identity.key}' already owns tasks on its "
                "current task board and cannot be rebound.",
            )

        with self._lock:
            self._board = task_board

    def assigned_tasks(self) -> tuple[AgentTask, ...]:
        """Return every task ever assigned to this agent."""

        return self.task_board.tasks_for_agent(
            self._identity.key,
        )

    def active_tasks(self) -> tuple[AgentTask, ...]:
        """Return the unfinished tasks of this agent, most urgent first."""

        return self.task_board.active_tasks(
            self._identity.key,
        )

    def active_task(self) -> AgentTask | None:
        """Return the single task the agent reports as its current work."""

        return self.task_board.primary_active_task(
            self._identity.key,
        )

    def last_finished_task(self) -> AgentTask | None:
        """Return the most recent finished task not yet acknowledged."""

        with self._lock:
            acknowledged = frozenset(
                self._acknowledged_task_ids,
            )

        finished = [
            task
            for task in self.assigned_tasks()
            if task.is_terminal and task.task_id not in acknowledged
        ]

        if not finished:
            return None

        return max(
            finished,
            key=lambda task: (task.updated_at, task.task_id),
        )

    def snapshot(self) -> AgentSnapshot:
        """Return the current status derived from the task board."""

        active_tasks = self.active_tasks()
        reference = (
            active_tasks[0]
            if active_tasks
            else self.last_finished_task()
        )

        with self._lock:
            stopped = self._stopped
            stop_note = self._stop_note
            updated_at = self._local_changed_at

        if stopped:
            state = AgentState.STOPPED
            message = stop_note or DEFAULT_STOP_MESSAGE
        elif reference is None:
            state = AgentState.IDLE
            message = IDLE_AGENT_MESSAGE
        else:
            state = _AGENT_STATE_BY_TASK_STATUS[reference.status]
            message = _task_message(reference)

        if reference is not None:
            updated_at = max(
                updated_at,
                reference.updated_at,
            )

        return AgentSnapshot(
            identity=self._identity,
            state=state,
            message=message,
            current_task=(
                reference.title
                if reference is not None
                else None
            ),
            current_task_id=(
                reference.task_id
                if reference is not None
                else None
            ),
            active_task_count=len(active_tasks),
            progress_percent=(
                reference.progress_percent
                if reference is not None
                else 0.0
            ),
            updated_at=updated_at,
        )

    def is_addressed_by(
        self,
        spoken_name: str,
    ) -> bool:
        """Return whether a spoken or written name addresses this agent."""

        normalized = spoken_name.strip().casefold()

        if not normalized:
            return False

        accepted_names = {
            self._identity.name.casefold(),
            self._identity.key.casefold(),
            *(
                wake_name.casefold()
                for wake_name in self._identity.wake_names
            ),
        }

        return normalized in accepted_names

    def reply_when_called(
        self,
        spoken_name: str,
    ) -> str | None:
        """Reply with the current status when called by name."""

        if not self.is_addressed_by(spoken_name):
            return None

        return self.status_reply()

    def status_reply(self) -> str:
        """Return a Lebanese-Arabic description of current work."""

        snapshot = self.snapshot()
        agent_name = snapshot.identity.name

        if snapshot.state is AgentState.IDLE:
            return (
                f"{agent_name}: أنا حاضر. "
                "ما عندي مهمة شغّالة هلق."
            )

        task_text = (
            snapshot.current_task
            or "المهمة الحالية"
        )

        if snapshot.state is AgentState.ASSIGNED:
            return (
                f"{agent_name}: عندي مهمة مسندة إلي: {task_text}. "
                f"{snapshot.message}"
            )

        if snapshot.state is AgentState.WORKING:
            return (
                f"{agent_name}: أنا عم اشتغل على {task_text}. "
                f"التقدّم {snapshot.progress_percent:.0f}%. "
                f"{snapshot.message}"
            )

        if snapshot.state is AgentState.WAITING:
            return (
                f"{agent_name}: أنا ناطر بخصوص {task_text}. "
                f"{snapshot.message}"
            )

        if snapshot.state is AgentState.COMPLETED:
            completed_text = (
                snapshot.current_task
                or "المهمة الأخيرة"
            )

            return (
                f"{agent_name}: خلّصت {completed_text}. "
                f"{snapshot.message}"
            )

        if snapshot.state is AgentState.CANCELLED:
            return (
                f"{agent_name}: انلغت مهمة {task_text}. "
                f"{snapshot.message}"
            )

        if snapshot.state is AgentState.ERROR:
            return (
                f"{agent_name}: صار معي خطأ خلال {task_text}. "
                f"{snapshot.message}"
            )

        return (
            f"{agent_name}: أنا موقوف حاليًا. "
            f"{snapshot.message}"
        )

    def tasks_reply(self) -> str:
        """Return a truthful list of the real tasks owned by this agent."""

        agent_name = self._identity.name
        active_tasks = self.active_tasks()

        if not active_tasks:
            finished = self.last_finished_task()

            if finished is None:
                return (
                    f"{agent_name}: ما عندي أي مهمة مسندة إلي هلق."
                )

            return (
                f"{agent_name}: ما عندي مهمة شغّالة. "
                f"آخر مهمة: {finished.title} "
                f"({finished.status.value})."
            )

        lines = [
            f"{agent_name}: عندي {len(active_tasks)} مهمة شغّالة:",
        ]

        lines.extend(
            (
                f"- [{task.task_id}] {task.title} "
                f"({task.status.value}, {task.priority.value}, "
                f"{task.progress_percent:.0f}%)"
            )
            for task in active_tasks
        )

        return "\n".join(lines)

    def start_task(
        self,
        task: str,
        *,
        message: str = "بلّشت تنفيذ المهمة.",
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> AgentSnapshot:
        """Create, claim, and start one new task on the shared board."""

        normalized_task = task.strip()

        if not normalized_task:
            raise ValueError(
                "Agent task cannot be empty.",
            )

        if self.active_task() is not None:
            raise RuntimeError(
                f"Agent '{self._identity.key}' already has an active task. "
                "Use the task board to run more than one task at a time.",
            )

        created = self.task_board.create_task(
            title=normalized_task,
            priority=priority,
            required_agent_key=self._identity.key,
        )

        self.task_board.assign_task(
            created.task_id,
            self._identity.key,
        )

        self.task_board.start_task(
            created.task_id,
            note=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def start_assigned_task(
        self,
        task_id: str | None = None,
        *,
        message: str = "بلّشت تنفيذ المهمة.",
    ) -> AgentSnapshot:
        """Start a task that Atlas already assigned to this agent."""

        task = (
            self.task_board.get_task(task_id)
            if task_id is not None
            else self._next_assigned_task()
        )

        if task.assigned_agent_key != self._identity.key:
            raise ValueError(
                f"Task '{task.task_id}' is not assigned to agent "
                f"'{self._identity.key}'.",
            )

        self.task_board.start_task(
            task.task_id,
            note=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def update_progress(
        self,
        progress_percent: float,
        *,
        message: str = "المهمة بعدها قيد التنفيذ.",
    ) -> AgentSnapshot:
        """Update progress for the currently active task."""

        task = self._require_active_task("update")

        self.task_board.update_progress(
            self._ensure_started(task).task_id,
            progress_percent,
            note=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def wait(
        self,
        *,
        message: str,
    ) -> AgentSnapshot:
        """Mark the agent as waiting without losing its current task."""

        task = self._require_active_task("pause")

        self.task_board.wait_task(
            self._ensure_started(task).task_id,
            note=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def complete_task(
        self,
        *,
        message: str = "المهمة خلصت بنجاح.",
    ) -> AgentSnapshot:
        """Mark the current task as completed."""

        task = self._require_active_task("complete")

        self.task_board.complete_task(
            self._ensure_started(task).task_id,
            result_summary=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def fail_task(
        self,
        *,
        message: str,
    ) -> AgentSnapshot:
        """Mark the current task as failed."""

        task = self._require_active_task("fail")

        self.task_board.fail_task(
            task.task_id,
            error_message=message,
        )

        self._clear_stop_flag()

        return self.snapshot()

    def reset(self) -> AgentSnapshot:
        """Cancel outstanding work and return the agent to an idle state."""

        for task in self.active_tasks():
            current = self.task_board.get_task(task.task_id)

            if current.is_terminal:
                continue

            self.task_board.cancel_task(current.task_id)

        finished_ids = {
            task.task_id
            for task in self.assigned_tasks()
            if task.is_terminal
        }

        with self._lock:
            self._acknowledged_task_ids.update(finished_ids)
            self._stopped = False
            self._stop_note = None
            self._local_changed_at = datetime.now(UTC)

        return self.snapshot()

    def stop(
        self,
        *,
        message: str = DEFAULT_STOP_MESSAGE,
    ) -> AgentSnapshot:
        """Stop the agent while preserving the current task context."""

        normalized_message = message.strip()

        with self._lock:
            self._stopped = True
            self._stop_note = normalized_message or None
            self._local_changed_at = datetime.now(UTC)

        return self.snapshot()

    def _clear_stop_flag(self) -> None:
        """Clear the stopped flag after the agent performs real work."""

        with self._lock:
            self._stopped = False
            self._stop_note = None
            self._local_changed_at = datetime.now(UTC)

    def _require_active_task(
        self,
        action: str,
    ) -> AgentTask:
        """Return the current active task or raise a readable error."""

        task = self.active_task()

        if task is None:
            raise RuntimeError(
                f"The agent has no active task to {action}.",
            )

        return task

    def _next_assigned_task(self) -> AgentTask:
        """Return the next task waiting to be started by this agent."""

        for task in self.active_tasks():
            if task.status is TaskStatus.ASSIGNED:
                return task

        raise RuntimeError(
            f"Agent '{self._identity.key}' has no assigned task to start.",
        )

    def _ensure_started(
        self,
        task: AgentTask,
    ) -> AgentTask:
        """Start an assigned task before it reports progress or results."""

        if task.status is not TaskStatus.ASSIGNED:
            return task

        return self.task_board.start_task(
            task.task_id,
        )


def _task_message(
    task: AgentTask,
) -> str:
    """Return the most truthful status message for one task."""

    if task.status is TaskStatus.COMPLETED and task.result_summary is not None:
        return task.result_summary

    if task.status is TaskStatus.FAILED and task.error_message is not None:
        return task.error_message

    return (
        task.status_note
        or _DEFAULT_NOTE_BY_TASK_STATUS[task.status]
    )
