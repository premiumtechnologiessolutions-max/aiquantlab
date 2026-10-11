from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import BacktestMetrics
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.strategies import StrategyDescriptor
from ai_quant_lab.validation import ValidationReport


class StrategyLifecycle(StrEnum):
    """Immutable strategy-version lifecycle values."""

    RESEARCH = "research"
    CANDIDATE = "candidate"
    CHALLENGER = "challenger"
    CHAMPION = "champion"
    SHADOW = "shadow"
    PAPER = "paper"
    SUSPENDED = "suspended"
    RETIRED = "retired"
    REACTIVATED = "reactivated"
    REJECTED = "rejected"


_ALLOWED_TRANSITIONS: dict[StrategyLifecycle, frozenset[StrategyLifecycle]] = {
    StrategyLifecycle.RESEARCH: frozenset(
        {StrategyLifecycle.CANDIDATE, StrategyLifecycle.REJECTED}
    ),
    StrategyLifecycle.CANDIDATE: frozenset(
        {StrategyLifecycle.CHALLENGER, StrategyLifecycle.REJECTED}
    ),
    StrategyLifecycle.CHALLENGER: frozenset(
        {
            StrategyLifecycle.CHAMPION,
            StrategyLifecycle.SHADOW,
            StrategyLifecycle.SUSPENDED,
            StrategyLifecycle.REJECTED,
        }
    ),
    StrategyLifecycle.CHAMPION: frozenset(
        {
            StrategyLifecycle.SHADOW,
            StrategyLifecycle.SUSPENDED,
            StrategyLifecycle.RETIRED,
        }
    ),
    StrategyLifecycle.SHADOW: frozenset(
        {
            StrategyLifecycle.PAPER,
            StrategyLifecycle.SUSPENDED,
            StrategyLifecycle.REJECTED,
        }
    ),
    StrategyLifecycle.PAPER: frozenset(
        {StrategyLifecycle.SUSPENDED, StrategyLifecycle.RETIRED}
    ),
    StrategyLifecycle.SUSPENDED: frozenset(
        {StrategyLifecycle.REACTIVATED, StrategyLifecycle.RETIRED}
    ),
    StrategyLifecycle.REACTIVATED: frozenset(
        {StrategyLifecycle.CHALLENGER, StrategyLifecycle.SUSPENDED}
    ),
    StrategyLifecycle.RETIRED: frozenset(),
    StrategyLifecycle.REJECTED: frozenset(),
}


class StrategyVersion(BaseModel):
    """Immutable code/config identity and current governed lifecycle status."""

    model_config = ConfigDict(frozen=True)

    version_id: str
    descriptor: StrategyDescriptor
    code_commit: str = Field(min_length=1)
    status: StrategyLifecycle = StrategyLifecycle.RESEARCH
    parent_version_id: str | None = None
    status_reason: str = "Initial research version."
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperimentRecord(BaseModel):
    """One append-only experiment result linked to exact data and strategy."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    strategy_version_id: str
    pair: ForexPair
    timeframe: Timeframe
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics: BacktestMetrics
    validation: ValidationReport
    json_report_path: str
    markdown_report_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperimentRegistry:
    """SQLite registry that never deletes failed versions or experiments."""

    def __init__(self, path: str | Path = "data/experiments/registry.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def register_strategy(
        self,
        *,
        descriptor: StrategyDescriptor,
        code_commit: str,
        parent_version_id: str | None = None,
    ) -> StrategyVersion:
        """Register or return one content-addressed immutable strategy version."""

        normalized_commit = code_commit.strip()

        if not normalized_commit:
            raise ValueError("A strategy version requires a code commit or build ID.")

        if parent_version_id is not None:
            self.get_strategy(parent_version_id)

        identity = (
            f"{descriptor.model_dump_json()}|{normalized_commit}|"
            f"{parent_version_id or ''}"
        )
        version_id = f"strategy_{sha256(identity.encode('utf-8')).hexdigest()[:16]}"

        try:
            return self.get_strategy(version_id)
        except KeyError:
            version = StrategyVersion(
                version_id=version_id,
                descriptor=descriptor,
                code_commit=normalized_commit,
                parent_version_id=parent_version_id,
            )

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO strategy_versions(version_id, payload, created_at) "
                "VALUES (?, ?, ?)",
                (version.version_id, version.model_dump_json(), version.created_at.isoformat()),
            )

        return version

    def transition_strategy(
        self,
        version_id: str,
        *,
        new_status: StrategyLifecycle,
        reason: str,
        human_approved: bool = False,
    ) -> StrategyVersion:
        """Apply one governed lifecycle transition without changing version code."""

        current = self.get_strategy(version_id)
        normalized_reason = reason.strip()

        if not normalized_reason:
            raise ValueError("A lifecycle transition requires a reason.")

        allowed = _ALLOWED_TRANSITIONS.get(current.status)

        if allowed is None or new_status not in allowed:
            raise ValueError(
                f"Strategy cannot transition from '{current.status}' to '{new_status}'.",
            )

        if new_status is StrategyLifecycle.PAPER and not human_approved:
            raise PermissionError("Paper promotion requires explicit human approval.")

        updated = current.model_copy(
            update={
                "status": new_status,
                "status_reason": normalized_reason,
                "updated_at": datetime.now(UTC),
            }
        )

        with self._connection() as connection:
            connection.execute(
                "UPDATE strategy_versions SET payload = ? WHERE version_id = ?",
                (updated.model_dump_json(), updated.version_id),
            )

        return updated

    def record_experiment(self, record: ExperimentRecord) -> ExperimentRecord:
        """Append one experiment, rejecting identifier reuse even if payload matches."""

        self.get_strategy(record.strategy_version_id)

        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO experiments(experiment_id, payload, created_at) "
                    "VALUES (?, ?, ?)",
                    (
                        record.experiment_id,
                        record.model_dump_json(),
                        record.created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError(
                    f"Experiment '{record.experiment_id}' already exists.",
                ) from error

        return record

    def get_strategy(self, version_id: str) -> StrategyVersion:
        """Return one strategy version by immutable identifier."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM strategy_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Strategy version '{version_id}' does not exist.")

        return StrategyVersion.model_validate_json(row[0])

    def list_strategies(self) -> tuple[StrategyVersion, ...]:
        """Return all strategy versions, including rejected and retired rows."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM strategy_versions ORDER BY created_at, version_id",
            ).fetchall()

        return tuple(StrategyVersion.model_validate_json(row[0]) for row in rows)

    def list_experiments(self) -> tuple[ExperimentRecord, ...]:
        """Return all experiments in append order."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM experiments ORDER BY created_at, experiment_id",
            ).fetchall()

        return tuple(ExperimentRecord.model_validate_json(row[0]) for row in rows)

    def _initialize(self) -> None:
        """Create the append-only registry schema if needed."""

        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS strategy_versions (
                    version_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a short serialized registry transaction."""

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
