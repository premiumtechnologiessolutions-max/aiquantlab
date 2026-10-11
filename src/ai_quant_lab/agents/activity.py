from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from enum import StrEnum
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_quant_lab.agents.identifiers import normalize_identifier
from ai_quant_lab.agents.messages import AgentMessage
from ai_quant_lab.agents.tasks import AgentTask


class ActivityType(StrEnum):
    """Auditable operational events emitted by the agent runtime."""

    TASK_CREATED = "task_created"
    TASK_CHANGED = "task_changed"
    MESSAGE_SENT = "message_sent"
    MESSAGE_READ = "message_read"
    HEARTBEAT = "heartbeat"
    RUNTIME_STARTED = "runtime_started"
    RUNTIME_STOPPED = "runtime_stopped"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"


class ActivityEvent(BaseModel):
    """One immutable fact in the operational audit trail."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: ActivityType
    actor_key: str
    message: str = Field(min_length=1)
    subject_id: str | None = None
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("event_id", "actor_key", "subject_id")
    @classmethod
    def normalize_ids(
        cls,
        value: str | None,
    ) -> str | None:
        """Normalize event, actor, and optional subject identifiers."""

        if value is None:
            return None

        return normalize_identifier(value, field_name="Activity identifier")

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        """Reject blank activity descriptions."""

        normalized = value.strip()

        if not normalized:
            raise ValueError("Activity message cannot be empty.")

        return normalized

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        """Require timezone-aware event timestamps and normalize to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Activity timestamps must include timezone information.")

        return value.astimezone(UTC)


class ActivityJournal:
    """Thread-safe task/message journal with truthful daily summaries."""

    def __init__(
        self,
        events: Iterable[ActivityEvent] = (),
        persist: Callable[[ActivityEvent], None] | None = None,
    ) -> None:
        self._lock = RLock()
        self._events: dict[str, ActivityEvent] = {}
        self._event_counter = 0
        self._persist = persist

        for event in events:
            if event.event_id in self._events:
                raise ValueError(f"Duplicate activity event '{event.event_id}'.")

            self._events[event.event_id] = event
            self._advance_counter(event.event_id)

    def record(
        self,
        *,
        event_type: ActivityType,
        actor_key: str,
        message: str,
        subject_id: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> ActivityEvent:
        """Append and optionally persist one immutable audit fact."""

        with self._lock:
            event = ActivityEvent(
                event_id=self._next_event_id(),
                event_type=event_type,
                actor_key=actor_key,
                subject_id=subject_id,
                message=message,
                metadata=metadata or {},
            )
            self._events[event.event_id] = event

            if self._persist is not None:
                self._persist(event)

            return event

    def on_task_changed(
        self,
        previous: AgentTask | None,
        current: AgentTask,
    ) -> None:
        """Record one TaskBoard listener notification."""

        event_type = (
            ActivityType.TASK_CREATED
            if previous is None
            else ActivityType.TASK_CHANGED
        )
        actor = current.assigned_agent_key or current.required_agent_key or "atlas"

        self.record(
            event_type=event_type,
            actor_key=actor,
            subject_id=current.task_id,
            message=f"Task '{current.title}' is {current.status.value}.",
            metadata={
                "status": current.status.value,
                "progress_percent": current.progress_percent,
            },
        )

    def on_message_changed(
        self,
        previous: AgentMessage | None,
        current: AgentMessage,
    ) -> None:
        """Record one message delivery or read receipt."""

        self.record(
            event_type=(
                ActivityType.MESSAGE_SENT
                if previous is None
                else ActivityType.MESSAGE_READ
            ),
            actor_key=(
                current.sender_key
                if previous is None
                else current.recipient_key
            ),
            subject_id=current.message_id,
            message=(
                f"Message sent to {current.recipient_key}: {current.subject}."
                if previous is None
                else f"Message from {current.sender_key} was read."
            ),
            metadata={"task_id": current.task_id},
        )

    def all_events(self) -> tuple[ActivityEvent, ...]:
        """Return the complete audit trail in append order."""

        with self._lock:
            return tuple(self._events.values())

    def events_for_day(self, day: date) -> tuple[ActivityEvent, ...]:
        """Return events whose UTC calendar date matches the requested day."""

        with self._lock:
            return tuple(
                event
                for event in self._events.values()
                if event.created_at.date() == day
            )

    def daily_summary(self, day: date | None = None) -> str:
        """Describe recorded work for one UTC day without inventing activity."""

        resolved_day = day or datetime.now(UTC).date()
        events = self.events_for_day(resolved_day)

        if not events:
            return f"ما في نشاط مسجّل بتاريخ {resolved_day.isoformat()}."

        task_events = [
            event
            for event in events
            if event.event_type in {ActivityType.TASK_CREATED, ActivityType.TASK_CHANGED}
        ]
        completed = sum(
            event.metadata.get("status") == "completed"
            for event in task_events
        )
        failed = sum(
            event.metadata.get("status") == "failed"
            for event in task_events
        )

        return (
            f"بتاريخ {resolved_day.isoformat()} تسجّل {len(events)} حدث: "
            f"{completed} إكمال مهام و{failed} فشل. "
            "التفاصيل مأخوذة من سجل التشغيل الفعلي."
        )

    def _next_event_id(self) -> str:
        """Generate a collision-free sequential event identifier."""

        self._event_counter += 1

        return f"event_{self._event_counter:09d}"

    def _advance_counter(self, event_id: str) -> None:
        """Keep automatic IDs ahead of restored sequential IDs."""

        prefix = "event_"

        if event_id.startswith(prefix) and event_id[len(prefix) :].isdigit():
            self._event_counter = max(
                self._event_counter,
                int(event_id[len(prefix) :]),
            )
