from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict

from ai_quant_lab.agents import ActivityEvent, AgentMessage, AgentTask


class RuntimeHeartbeat(BaseModel):
    """Last known liveness signal of one runtime component."""

    model_config = ConfigDict(frozen=True)

    component_key: str
    status: str
    observed_at: datetime


class SQLiteOperationalStore:
    """Durable SQLite storage for tasks, messages, events, and heartbeats."""

    def __init__(self, path: str | Path = "data/operational/lab.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize_schema()

    def on_task_changed(
        self,
        previous: AgentTask | None,
        current: AgentTask,
    ) -> None:
        """Persist the newest immutable snapshot of one task."""

        del previous
        payload = current.model_dump_json()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks(task_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (current.task_id, payload, current.updated_at.isoformat()),
            )

    def on_message_changed(
        self,
        previous: AgentMessage | None,
        current: AgentMessage,
    ) -> None:
        """Persist the newest immutable snapshot of one message."""

        del previous
        payload = current.model_dump_json()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO messages(message_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (current.message_id, payload, datetime.now(UTC).isoformat()),
            )

    def append_event(self, event: ActivityEvent) -> None:
        """Append one immutable activity event without overwriting history."""

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO activity_events(event_id, payload, created_at)
                VALUES (?, ?, ?)
                """,
                (event.event_id, event.model_dump_json(), event.created_at.isoformat()),
            )

    def save_heartbeat(
        self,
        component_key: str,
        *,
        status: str = "healthy",
        observed_at: datetime | None = None,
    ) -> RuntimeHeartbeat:
        """Upsert the last liveness record for one component."""

        resolved_time = observed_at or datetime.now(UTC)
        heartbeat = RuntimeHeartbeat(
            component_key=component_key,
            status=status,
            observed_at=resolved_time,
        )

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO heartbeats(component_key, status, observed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(component_key) DO UPDATE SET
                    status = excluded.status,
                    observed_at = excluded.observed_at
                """,
                (component_key, status, resolved_time.isoformat()),
            )

        return heartbeat

    def load_tasks(self) -> tuple[AgentTask, ...]:
        """Load the latest task snapshots in creation order."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM tasks ORDER BY updated_at, task_id",
            ).fetchall()

        tasks = tuple(AgentTask.model_validate_json(row[0]) for row in rows)

        return tuple(sorted(tasks, key=lambda task: (task.created_at, task.task_id)))

    def load_messages(self) -> tuple[AgentMessage, ...]:
        """Load the latest message snapshots in delivery order."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM messages ORDER BY updated_at, message_id",
            ).fetchall()

        messages = tuple(AgentMessage.model_validate_json(row[0]) for row in rows)

        return tuple(sorted(messages, key=lambda item: (item.created_at, item.message_id)))

    def load_events(self) -> tuple[ActivityEvent, ...]:
        """Load the append-only operational audit trail."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM activity_events ORDER BY created_at, event_id",
            ).fetchall()

        return tuple(ActivityEvent.model_validate_json(row[0]) for row in rows)

    def load_heartbeats(self) -> tuple[RuntimeHeartbeat, ...]:
        """Load the current heartbeat state for every component."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT component_key, status, observed_at "
                "FROM heartbeats ORDER BY component_key",
            ).fetchall()

        return tuple(
            RuntimeHeartbeat(
                component_key=row[0],
                status=row[1],
                observed_at=datetime.fromisoformat(row[2]),
            )
            for row in rows
        )

    def _initialize_schema(self) -> None:
        """Create the operational schema without destroying existing rows."""

        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activity_events (
                    event_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS heartbeats (
                    component_key TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a short transaction protected across local runtime threads."""

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
