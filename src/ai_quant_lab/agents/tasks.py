from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ai_quant_lab.agents.identifiers import normalize_identifier


class TaskStatus(StrEnum):
    """Lifecycle status of one agent task."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    """Execution priority of one agent task."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


ACTIVE_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.ASSIGNED,
        TaskStatus.RUNNING,
        TaskStatus.WAITING,
    }
)

TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    }
)

_PRIORITY_ORDER: dict[TaskPriority, int] = {
    TaskPriority.CRITICAL: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}

_ATTENTION_ORDER: dict[TaskStatus, int] = {
    TaskStatus.RUNNING: 0,
    TaskStatus.WAITING: 1,
    TaskStatus.ASSIGNED: 2,
    TaskStatus.PENDING: 3,
    TaskStatus.COMPLETED: 4,
    TaskStatus.FAILED: 5,
    TaskStatus.CANCELLED: 6,
}


class AgentTask(BaseModel):
    """Immutable work item assigned to an AI Quant Lab agent."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)

    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING

    required_agent_key: str | None = None
    assigned_agent_key: str | None = None
    parent_task_id: str | None = None

    progress_percent: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
    )

    tags: tuple[str, ...] = ()

    status_note: str | None = None
    result_summary: str | None = None
    error_message: str | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @field_validator("task_id")
    @classmethod
    def normalize_task_id(
        cls,
        value: str,
    ) -> str:
        """Normalize and validate the task identifier."""

        return normalize_identifier(
            value,
            field_name="Task ID",
        )

    @field_validator(
        "required_agent_key",
        "assigned_agent_key",
        "parent_task_id",
    )
    @classmethod
    def normalize_optional_identifier(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize optional task and agent identifiers."""

        if value is None:
            return None

        return normalize_identifier(
            value,
            field_name="Identifier",
        )

    @field_validator("title", "description")
    @classmethod
    def normalize_required_text(
        cls,
        value: str,
    ) -> str:
        """Normalize required task text."""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Task text cannot be empty.",
            )

        return normalized

    @field_validator(
        "status_note",
        "result_summary",
        "error_message",
    )
    @classmethod
    def normalize_optional_text(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize optional task result text."""

        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            return None

        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Normalize task tags and remove duplicates."""

        normalized_tags: list[str] = []
        known_tags: set[str] = set()

        for value in values:
            normalized = (
                value.strip()
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
            )

            if not normalized:
                raise ValueError(
                    "Task tags cannot be empty.",
                )

            if normalized in known_tags:
                continue

            known_tags.add(normalized)
            normalized_tags.append(normalized)

        return tuple(normalized_tags)

    @field_validator(
        "created_at",
        "updated_at",
    )
    @classmethod
    def normalize_timestamp(
        cls,
        value: datetime,
    ) -> datetime:
        """Require timezone information and normalize to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Task timestamps must include timezone information.",
            )

        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_task_state(self) -> Self:
        """Validate fields required by the current task status."""

        if self.updated_at < self.created_at:
            raise ValueError(
                "Task updated time cannot be earlier than creation time.",
            )

        if self.parent_task_id is not None and self.parent_task_id == self.task_id:
            raise ValueError(
                "A task cannot be its own parent task.",
            )

        if self.status is TaskStatus.PENDING:
            if self.assigned_agent_key is not None:
                raise ValueError(
                    "A pending task cannot have an assigned agent.",
                )

            if self.progress_percent != 0.0:
                raise ValueError(
                    "A pending task must have zero progress.",
                )

        if (
            self.status in ACTIVE_TASK_STATUSES | {TaskStatus.COMPLETED, TaskStatus.FAILED}
            and self.assigned_agent_key is None
        ):
            raise ValueError(
                "The current task status requires an assigned agent.",
            )

        if (
            self.assigned_agent_key is not None
            and self.required_agent_key is not None
            and self.assigned_agent_key != self.required_agent_key
        ):
            raise ValueError(
                "The assigned agent must match the required agent of the task.",
            )

        if self.status is TaskStatus.ASSIGNED and self.progress_percent != 0.0:
            raise ValueError(
                "A newly assigned task must have zero progress.",
            )

        if self.status is TaskStatus.COMPLETED:
            if self.progress_percent != 100.0:
                raise ValueError(
                    "A completed task must have 100 percent progress.",
                )

            if self.result_summary is None:
                raise ValueError(
                    "A completed task requires a result summary.",
                )

        elif self.result_summary is not None:
            raise ValueError(
                "Only a completed task can contain a result summary.",
            )

        if self.status is TaskStatus.FAILED:
            if self.error_message is None:
                raise ValueError(
                    "A failed task requires an error message.",
                )

        elif self.error_message is not None:
            raise ValueError(
                "Only a failed task can contain an error message.",
            )

        if (
            self.status is not TaskStatus.COMPLETED
            and self.progress_percent == 100.0
        ):
            raise ValueError(
                "Use completed status when task progress reaches 100 percent.",
            )

        return self

    @property
    def is_active(self) -> bool:
        """Return whether the task is assigned and not finished."""

        return self.status in ACTIVE_TASK_STATUSES

    @property
    def is_terminal(self) -> bool:
        """Return whether the task reached a final status."""

        return self.status in TERMINAL_TASK_STATUSES

    @property
    def is_pending(self) -> bool:
        """Return whether the task still waits for an assignment."""

        return self.status is TaskStatus.PENDING

    def attention_sort_key(
        self,
    ) -> tuple[int, int, datetime, str]:
        """Return the deterministic ordering key used to pick work."""

        return (
            _ATTENTION_ORDER[self.status],
            _PRIORITY_ORDER[self.priority],
            self.created_at,
            self.task_id,
        )


class TaskBoardListener(Protocol):
    """Observer notified after every committed task change.

    This is the extension point used by future persistence, message bus,
    and daily work journal services. Listeners are called while the board
    lock is held, so they must stay fast and must not call back into the
    same board.
    """

    def on_task_changed(
        self,
        previous: AgentTask | None,
        current: AgentTask,
    ) -> None:
        """Handle one committed task transition."""

        ...  # pragma: no cover


class TaskBoard:
    """Thread-safe task board used by Atlas and the agent team."""

    def __init__(
        self,
        listeners: Iterable[TaskBoardListener] = (),
    ) -> None:
        self._lock = RLock()
        self._tasks: dict[str, AgentTask] = {}
        self._task_counter = 0
        self._listeners: list[TaskBoardListener] = list(listeners)

    def add_listener(
        self,
        listener: TaskBoardListener,
    ) -> None:
        """Register one observer for future task changes."""

        with self._lock:
            self._listeners.append(listener)

    def restore_tasks(
        self,
        tasks: Iterable[AgentTask],
    ) -> None:
        """Restore validated task snapshots before runtime work begins.

        Restored rows are not published to listeners because they already
        represent committed historical state in persistent storage.
        """

        restored = tuple(tasks)
        known_ids = {task.task_id for task in restored}

        if len(known_ids) != len(restored):
            raise ValueError("Restored tasks contain duplicate identifiers.")

        for task in restored:
            if task.parent_task_id is not None and task.parent_task_id not in known_ids:
                raise ValueError(
                    f"Restored task '{task.task_id}' references missing parent "
                    f"'{task.parent_task_id}'.",
                )

        with self._lock:
            if self._tasks:
                raise RuntimeError("Tasks can only be restored into an empty board.")

            for task in sorted(restored, key=lambda item: (item.created_at, item.task_id)):
                self._tasks[task.task_id] = task
                self._advance_counter(task.task_id)

    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        required_agent_key: str | None = None,
        parent_task_id: str | None = None,
        tags: tuple[str, ...] = (),
        task_id: str | None = None,
    ) -> AgentTask:
        """Create and register one pending task."""

        with self._lock:
            resolved_task_id = (
                normalize_identifier(
                    task_id,
                    field_name="Task ID",
                )
                if task_id is not None
                else self._next_task_id()
            )

            if resolved_task_id in self._tasks:
                raise ValueError(
                    f"Task '{resolved_task_id}' already exists.",
                )

            if (
                parent_task_id is not None
                and normalize_identifier(
                    parent_task_id,
                    field_name="Parent task ID",
                )
                not in self._tasks
            ):
                raise KeyError(
                    f"Parent task '{parent_task_id}' does not exist.",
                )

            now = datetime.now(UTC)

            task = AgentTask(
                task_id=resolved_task_id,
                title=title,
                description=(
                    description
                    if description is not None
                    else title
                ),
                priority=priority,
                required_agent_key=required_agent_key,
                parent_task_id=parent_task_id,
                tags=tags,
                created_at=now,
                updated_at=now,
            )

            self._tasks[task.task_id] = task
            self._notify(None, task)

            return task

    def assign_task(
        self,
        task_id: str,
        agent_key: str,
    ) -> AgentTask:
        """Assign one pending task to an agent."""

        normalized_agent_key = normalize_identifier(
            agent_key,
            field_name="Agent key",
        )

        with self._lock:
            task = self._require_task(task_id)

            if task.status is not TaskStatus.PENDING:
                raise RuntimeError(
                    "Only a pending task can be assigned.",
                )

            if (
                task.required_agent_key is not None
                and task.required_agent_key != normalized_agent_key
            ):
                raise ValueError(
                    f"Task '{task.task_id}' requires agent "
                    f"'{task.required_agent_key}'.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.ASSIGNED,
                assigned_agent_key=normalized_agent_key,
            )

    def reassign_task(
        self,
        task_id: str,
        agent_key: str,
    ) -> AgentTask:
        """Move one active task to a different agent and restart it."""

        normalized_agent_key = normalize_identifier(
            agent_key,
            field_name="Agent key",
        )

        with self._lock:
            task = self._require_task(task_id)

            if not task.is_active:
                raise RuntimeError(
                    "Only an active task can be reassigned.",
                )

            if (
                task.required_agent_key is not None
                and task.required_agent_key != normalized_agent_key
            ):
                raise ValueError(
                    f"Task '{task.task_id}' requires agent "
                    f"'{task.required_agent_key}'.",
                )

            if task.assigned_agent_key == normalized_agent_key:
                raise ValueError(
                    f"Task '{task.task_id}' is already assigned to agent "
                    f"'{normalized_agent_key}'.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.ASSIGNED,
                assigned_agent_key=normalized_agent_key,
                progress_percent=0.0,
                status_note=None,
            )

    def release_task(
        self,
        task_id: str,
    ) -> AgentTask:
        """Return one active task to the shared pending backlog."""

        with self._lock:
            task = self._require_task(task_id)

            if not task.is_active:
                raise RuntimeError(
                    "Only an active task can be released.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.PENDING,
                assigned_agent_key=None,
                progress_percent=0.0,
                status_note=None,
            )

    def start_task(
        self,
        task_id: str,
        *,
        note: str | None = None,
    ) -> AgentTask:
        """Start or resume an assigned task."""

        with self._lock:
            task = self._require_task(task_id)

            if task.status not in {
                TaskStatus.ASSIGNED,
                TaskStatus.WAITING,
            }:
                raise RuntimeError(
                    "Only an assigned or waiting task can be started.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.RUNNING,
                status_note=(
                    note
                    if note is not None
                    else task.status_note
                ),
            )

    def update_progress(
        self,
        task_id: str,
        progress_percent: float,
        *,
        note: str | None = None,
    ) -> AgentTask:
        """Update progress for a running task."""

        if progress_percent < 0.0:
            raise ValueError(
                "Task progress cannot be below zero.",
            )

        if progress_percent >= 100.0:
            raise ValueError(
                "Use complete_task when progress reaches 100 percent.",
            )

        with self._lock:
            task = self._require_task(task_id)

            if task.status not in {
                TaskStatus.RUNNING,
                TaskStatus.WAITING,
            }:
                raise RuntimeError(
                    "Only a running or waiting task can receive "
                    "progress updates.",
                )

            if progress_percent < task.progress_percent:
                raise ValueError(
                    "Task progress cannot move backwards.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.RUNNING,
                progress_percent=progress_percent,
                status_note=(
                    note
                    if note is not None
                    else task.status_note
                ),
            )

    def wait_task(
        self,
        task_id: str,
        *,
        note: str | None = None,
    ) -> AgentTask:
        """Pause a running task while it waits for information."""

        with self._lock:
            task = self._require_task(task_id)

            if task.status is not TaskStatus.RUNNING:
                raise RuntimeError(
                    "Only a running task can be placed in waiting status.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.WAITING,
                status_note=(
                    note
                    if note is not None
                    else task.status_note
                ),
            )

    def complete_task(
        self,
        task_id: str,
        *,
        result_summary: str,
    ) -> AgentTask:
        """Complete one running or waiting task."""

        normalized_result = result_summary.strip()

        if not normalized_result:
            raise ValueError(
                "Completed task result cannot be empty.",
            )

        with self._lock:
            task = self._require_task(task_id)

            if task.status not in {
                TaskStatus.RUNNING,
                TaskStatus.WAITING,
            }:
                raise RuntimeError(
                    "Only a running or waiting task can be completed.",
                )

            blocking_child = self._first_unfinished_descendant(
                task.task_id,
            )

            if blocking_child is not None:
                raise RuntimeError(
                    f"Task '{task.task_id}' cannot be completed while subtask "
                    f"'{blocking_child.task_id}' is not finished.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.COMPLETED,
                progress_percent=100.0,
                result_summary=normalized_result,
            )

    def fail_task(
        self,
        task_id: str,
        *,
        error_message: str,
    ) -> AgentTask:
        """Mark an assigned or active task as failed."""

        normalized_error = error_message.strip()

        if not normalized_error:
            raise ValueError(
                "Failed task error message cannot be empty.",
            )

        with self._lock:
            task = self._require_task(task_id)

            if not task.is_active:
                raise RuntimeError(
                    "The current task cannot be marked as failed.",
                )

            return self._replace_task(
                task,
                status=TaskStatus.FAILED,
                error_message=normalized_error,
            )

    def cancel_task(
        self,
        task_id: str,
        *,
        cascade: bool = True,
    ) -> AgentTask:
        """Cancel a non-terminal task and, by default, its subtasks."""

        with self._lock:
            task = self._require_task(task_id)

            if task.is_terminal:
                raise RuntimeError(
                    "A terminal task cannot be cancelled.",
                )

            if cascade:
                for descendant in self._descendant_tasks(task.task_id):
                    if descendant.is_terminal:
                        continue

                    self._replace_task(
                        descendant,
                        status=TaskStatus.CANCELLED,
                        status_note=None,
                    )

            return self._replace_task(
                self._tasks[task.task_id],
                status=TaskStatus.CANCELLED,
                status_note=None,
            )

    def get_task(
        self,
        task_id: str,
    ) -> AgentTask:
        """Return one task using its identifier."""

        with self._lock:
            return self._require_task(task_id)

    def all_tasks(self) -> tuple[AgentTask, ...]:
        """Return all tasks in creation order."""

        with self._lock:
            return tuple(
                self._tasks.values(),
            )

    def tasks_for_agent(
        self,
        agent_key: str,
    ) -> tuple[AgentTask, ...]:
        """Return all tasks assigned to one agent."""

        normalized_agent_key = normalize_identifier(
            agent_key,
            field_name="Agent key",
        )

        with self._lock:
            return tuple(
                task
                for task in self._tasks.values()
                if task.assigned_agent_key == normalized_agent_key
            )

    def tasks_by_status(
        self,
        status: TaskStatus,
    ) -> tuple[AgentTask, ...]:
        """Return all tasks matching one status."""

        with self._lock:
            return tuple(
                task
                for task in self._tasks.values()
                if task.status is status
            )

    def active_tasks(
        self,
        agent_key: str | None = None,
    ) -> tuple[AgentTask, ...]:
        """Return active tasks ordered by the attention rules."""

        normalized_agent_key = (
            normalize_identifier(
                agent_key,
                field_name="Agent key",
            )
            if agent_key is not None
            else None
        )

        with self._lock:
            matching = [
                task
                for task in self._tasks.values()
                if task.is_active
                and (
                    normalized_agent_key is None
                    or task.assigned_agent_key == normalized_agent_key
                )
            ]

        return tuple(
            sorted(
                matching,
                key=AgentTask.attention_sort_key,
            )
        )

    def pending_tasks(self) -> tuple[AgentTask, ...]:
        """Return unassigned backlog tasks ordered by the attention rules."""

        with self._lock:
            matching = [
                task
                for task in self._tasks.values()
                if task.is_pending
            ]

        return tuple(
            sorted(
                matching,
                key=AgentTask.attention_sort_key,
            )
        )

    def primary_active_task(
        self,
        agent_key: str,
    ) -> AgentTask | None:
        """Return the single task an agent should report as current work."""

        active = self.active_tasks(agent_key)

        return active[0] if active else None

    def child_tasks(
        self,
        task_id: str,
    ) -> tuple[AgentTask, ...]:
        """Return the direct subtasks of one task in creation order."""

        with self._lock:
            parent = self._require_task(task_id)

            return tuple(
                task
                for task in self._tasks.values()
                if task.parent_task_id == parent.task_id
            )

    def descendant_tasks(
        self,
        task_id: str,
    ) -> tuple[AgentTask, ...]:
        """Return every subtask below one task in creation order."""

        with self._lock:
            parent = self._require_task(task_id)

            return self._descendant_tasks(parent.task_id)

    def _descendant_tasks(
        self,
        task_id: str,
    ) -> tuple[AgentTask, ...]:
        """Return every subtask below one known task identifier."""

        collected: dict[str, AgentTask] = {}
        frontier = [task_id]

        while frontier:
            current_id = frontier.pop()

            for task in self._tasks.values():
                if task.parent_task_id != current_id:
                    continue

                if task.task_id in collected:
                    continue

                collected[task.task_id] = task
                frontier.append(task.task_id)

        return tuple(
            task
            for task in self._tasks.values()
            if task.task_id in collected
        )

    def _first_unfinished_descendant(
        self,
        task_id: str,
    ) -> AgentTask | None:
        """Return the first subtask that still blocks parent completion."""

        for descendant in self._descendant_tasks(task_id):
            if not descendant.is_terminal:
                return descendant

        return None

    def _next_task_id(self) -> str:
        """Generate the next unused task identifier."""

        while True:
            self._task_counter += 1

            candidate = (
                f"task_{self._task_counter:06d}"
            )

            if candidate not in self._tasks:
                return candidate

    def _advance_counter(self, task_id: str) -> None:
        """Keep automatic IDs ahead of restored sequential IDs."""

        prefix = "task_"

        if task_id.startswith(prefix) and task_id[len(prefix) :].isdigit():
            self._task_counter = max(
                self._task_counter,
                int(task_id[len(prefix) :]),
            )

    def _require_task(
        self,
        task_id: str,
    ) -> AgentTask:
        """Return one task or raise a readable error."""

        normalized_task_id = normalize_identifier(
            task_id,
            field_name="Task ID",
        )

        task = self._tasks.get(
            normalized_task_id,
        )

        if task is None:
            raise KeyError(
                f"Task '{normalized_task_id}' does not exist.",
            )

        return task

    def _replace_task(
        self,
        task: AgentTask,
        **changes: object,
    ) -> AgentTask:
        """Create and store a validated replacement task."""

        task_data: dict[str, object] = task.model_dump(
            mode="python",
        )

        task_data.update(changes)
        task_data["updated_at"] = datetime.now(UTC)

        updated_task = AgentTask.model_validate(
            task_data,
        )

        self._tasks[updated_task.task_id] = updated_task
        self._notify(task, updated_task)

        return updated_task

    def _notify(
        self,
        previous: AgentTask | None,
        current: AgentTask,
    ) -> None:
        """Publish one committed task change to all listeners."""

        for listener in self._listeners:
            listener.on_task_changed(
                previous,
                current,
            )
