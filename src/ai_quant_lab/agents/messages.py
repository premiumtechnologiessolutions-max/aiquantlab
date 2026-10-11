from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_quant_lab.agents.identifiers import normalize_identifier


class AgentMessage(BaseModel):
    """Immutable internal message exchanged by agents or the user."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    sender_key: str
    recipient_key: str
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None

    @field_validator("message_id", "sender_key", "recipient_key", "task_id")
    @classmethod
    def normalize_ids(
        cls,
        value: str | None,
        info: object,
    ) -> str | None:
        """Normalize message, participant, and optional task identifiers."""

        if value is None:
            return None

        field_name = getattr(info, "field_name", "Identifier")

        return normalize_identifier(
            value,
            field_name=field_name.replace("_", " ").title(),
        )

    @field_validator("subject", "body")
    @classmethod
    def normalize_text(
        cls,
        value: str,
    ) -> str:
        """Reject empty message text after trimming."""

        normalized = value.strip()

        if not normalized:
            raise ValueError("Message text cannot be empty.")

        return normalized

    @field_validator("created_at", "read_at")
    @classmethod
    def normalize_timestamps(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        """Require timezone-aware message timestamps and normalize to UTC."""

        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Message timestamps must include timezone information.")

        return value.astimezone(UTC)


class AgentMessageBusListener(Protocol):
    """Observer notified after a message is sent or marked as read."""

    def on_message_changed(
        self,
        previous: AgentMessage | None,
        current: AgentMessage,
    ) -> None:
        """Handle one committed message change."""

        ...  # pragma: no cover


class AgentMessageBus:
    """Thread-safe inbox/outbox shared by the complete agent team."""

    def __init__(
        self,
        messages: Iterable[AgentMessage] = (),
        listeners: Iterable[AgentMessageBusListener] = (),
    ) -> None:
        self._lock = RLock()
        self._messages: dict[str, AgentMessage] = {}
        self._message_counter = 0
        self._listeners = list(listeners)

        for message in messages:
            if message.message_id in self._messages:
                raise ValueError(f"Duplicate message '{message.message_id}'.")

            self._messages[message.message_id] = message
            self._advance_counter(message.message_id)

    def add_listener(
        self,
        listener: AgentMessageBusListener,
    ) -> None:
        """Register one observer for future message changes."""

        with self._lock:
            self._listeners.append(listener)

    def send(
        self,
        *,
        sender_key: str,
        recipient_key: str,
        subject: str,
        body: str,
        task_id: str | None = None,
        message_id: str | None = None,
    ) -> AgentMessage:
        """Create and deliver one message to a recipient inbox."""

        with self._lock:
            resolved_id = (
                normalize_identifier(message_id, field_name="Message ID")
                if message_id is not None
                else self._next_message_id()
            )

            if resolved_id in self._messages:
                raise ValueError(f"Message '{resolved_id}' already exists.")

            message = AgentMessage(
                message_id=resolved_id,
                sender_key=sender_key,
                recipient_key=recipient_key,
                subject=subject,
                body=body,
                task_id=task_id,
            )
            self._messages[message.message_id] = message
            self._notify(None, message)

            return message

    def mark_read(
        self,
        message_id: str,
        *,
        reader_key: str,
    ) -> AgentMessage:
        """Mark a delivered message read by its intended recipient."""

        normalized_reader = normalize_identifier(reader_key, field_name="Reader key")

        with self._lock:
            previous = self.get_message(message_id)

            if previous.recipient_key != normalized_reader:
                raise PermissionError("Only the intended recipient can read this message.")

            if previous.read_at is not None:
                return previous

            current = previous.model_copy(update={"read_at": datetime.now(UTC)})
            self._messages[current.message_id] = current
            self._notify(previous, current)

            return current

    def get_message(self, message_id: str) -> AgentMessage:
        """Return one message by identifier."""

        normalized = normalize_identifier(message_id, field_name="Message ID")

        with self._lock:
            message = self._messages.get(normalized)

            if message is None:
                raise KeyError(f"Message '{normalized}' does not exist.")

            return message

    def inbox(
        self,
        recipient_key: str,
        *,
        unread_only: bool = False,
    ) -> tuple[AgentMessage, ...]:
        """Return one recipient's inbox in delivery order."""

        normalized = normalize_identifier(recipient_key, field_name="Recipient key")

        with self._lock:
            return tuple(
                message
                for message in self._messages.values()
                if message.recipient_key == normalized
                and (not unread_only or message.read_at is None)
            )

    def outbox(self, sender_key: str) -> tuple[AgentMessage, ...]:
        """Return one sender's outbox in delivery order."""

        normalized = normalize_identifier(sender_key, field_name="Sender key")

        with self._lock:
            return tuple(
                message
                for message in self._messages.values()
                if message.sender_key == normalized
            )

    def all_messages(self) -> tuple[AgentMessage, ...]:
        """Return every message in delivery order."""

        with self._lock:
            return tuple(self._messages.values())

    def _next_message_id(self) -> str:
        """Generate a collision-free sequential message identifier."""

        while True:
            self._message_counter += 1
            candidate = f"message_{self._message_counter:06d}"

            if candidate not in self._messages:
                return candidate

    def _advance_counter(self, message_id: str) -> None:
        """Keep automatic IDs ahead of restored sequential IDs."""

        prefix = "message_"

        if message_id.startswith(prefix) and message_id[len(prefix) :].isdigit():
            self._message_counter = max(
                self._message_counter,
                int(message_id[len(prefix) :]),
            )

    def _notify(
        self,
        previous: AgentMessage | None,
        current: AgentMessage,
    ) -> None:
        """Publish one committed message change."""

        for listener in self._listeners:
            listener.on_message_changed(previous, current)
