from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents.identifiers import normalize_identifier


class ScheduledJobSnapshot(BaseModel):
    """Serializable status of one recurring deterministic runtime job."""

    model_config = ConfigDict(frozen=True)

    job_key: str
    interval_seconds: float = Field(gt=0)
    next_run_at: datetime
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_error: str | None = None
    run_count: int = Field(default=0, ge=0)


class ScheduledJob:
    """One bounded recurring callback owned by the runtime scheduler."""

    def __init__(
        self,
        *,
        job_key: str,
        interval_seconds: float,
        callback: Callable[[], object],
        first_run_at: datetime | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Job interval must be greater than zero.")

        self.job_key = normalize_identifier(job_key, field_name="Job key")
        self.interval_seconds = interval_seconds
        self.callback = callback
        self.next_run_at = first_run_at or datetime.now(UTC)
        self.last_started_at: datetime | None = None
        self.last_completed_at: datetime | None = None
        self.last_error: str | None = None
        self.run_count = 0

    def snapshot(self) -> ScheduledJobSnapshot:
        """Return the current serializable job state."""

        return ScheduledJobSnapshot(
            job_key=self.job_key,
            interval_seconds=self.interval_seconds,
            next_run_at=self.next_run_at,
            last_started_at=self.last_started_at,
            last_completed_at=self.last_completed_at,
            last_error=self.last_error,
            run_count=self.run_count,
        )


class RuntimeScheduler:
    """Thread-safe scheduler that runs each due job at most once per tick."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, ScheduledJob] = {}

    def register(self, job: ScheduledJob) -> None:
        """Register one uniquely named recurring job."""

        with self._lock:
            if job.job_key in self._jobs:
                raise ValueError(f"Scheduled job '{job.job_key}' already exists.")

            self._jobs[job.job_key] = job

    def run_due(
        self,
        now: datetime | None = None,
    ) -> tuple[ScheduledJobSnapshot, ...]:
        """Run all callbacks due at the supplied UTC time."""

        resolved_now = now or datetime.now(UTC)

        with self._lock:
            due = [
                job
                for job in self._jobs.values()
                if job.next_run_at <= resolved_now
            ]

        snapshots: list[ScheduledJobSnapshot] = []

        for job in due:
            job.last_started_at = resolved_now
            job.last_error = None

            try:
                job.callback()
            except Exception as error:  # noqa: BLE001 - scheduler isolates job failures
                job.last_error = f"{type(error).__name__}: {error}"
            else:
                job.last_completed_at = datetime.now(UTC)
            finally:
                job.run_count += 1
                job.next_run_at = resolved_now + timedelta(seconds=job.interval_seconds)
                snapshots.append(job.snapshot())

        return tuple(snapshots)

    def snapshots(self) -> tuple[ScheduledJobSnapshot, ...]:
        """Return every registered job in registration order."""

        with self._lock:
            return tuple(job.snapshot() for job in self._jobs.values())
