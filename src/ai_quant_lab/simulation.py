from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.risk import RiskLimits
from ai_quant_lab.strategies import PositionSignal


class SimulationMode(StrEnum):
    """Permitted non-live observation and execution modes."""

    SHADOW = "shadow"
    PAPER = "paper"


class SimulationStatus(StrEnum):
    """Outcome of one simulated strategy decision."""

    OBSERVED = "observed"
    FILLED = "filled"
    REJECTED = "rejected"


class MarketQuote(BaseModel):
    """Timestamped bid/ask snapshot used by deterministic simulation."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)

    @model_validator(mode="after")
    def ask_must_not_be_below_bid(self) -> MarketQuote:
        """Reject structurally invalid quotes."""

        if self.ask < self.bid:
            raise ValueError("Ask price cannot be below bid price.")

        return self


class SimulationPolicy(BaseModel):
    """Execution-quality limits applied before a paper fill is accepted."""

    model_config = ConfigDict(frozen=True)

    maximum_quote_age_seconds: float = Field(default=30.0, gt=0)
    maximum_spread_points: float = Field(default=50.0, gt=0)
    slippage_points: float = Field(default=1.0, ge=0)
    point_size: float = Field(default=0.00001, gt=0)


class SimulationDecision(BaseModel):
    """Append-only record of a shadow observation or simulated paper fill."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    mode: SimulationMode
    status: SimulationStatus
    pair: ForexPair
    timeframe: Timeframe
    strategy_version_id: str
    signal: PositionSignal
    requested_units: float = Field(gt=0)
    quote: MarketQuote
    spread_points: float = Field(ge=0)
    simulated_fill_price: float | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SimulationLedger:
    """Append-only SQLite ledger with no connection to broker order APIs."""

    def __init__(self, path: str | Path = "data/simulation/ledger.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def submit(
        self,
        *,
        mode: SimulationMode,
        pair: ForexPair,
        timeframe: Timeframe,
        strategy_version_id: str,
        signal: PositionSignal,
        requested_units: float,
        quote: MarketQuote,
        policy: SimulationPolicy | None = None,
        risk_limits: RiskLimits | None = None,
        observed_at: datetime | None = None,
    ) -> SimulationDecision:
        """Validate and append one safe shadow or paper decision."""

        if requested_units <= 0:
            raise ValueError("Requested simulation units must be greater than zero.")

        resolved_policy = policy or SimulationPolicy(
            point_size=(0.001 if pair.endswith("JPY") else 0.00001)
        )
        resolved_limits = risk_limits or RiskLimits()
        now = observed_at or datetime.now(UTC)
        quote_age = (now - quote.timestamp).total_seconds()
        spread_points = (quote.ask - quote.bid) / resolved_policy.point_size
        status = SimulationStatus.OBSERVED
        fill_price: float | None = None
        reason = "Signal recorded in shadow mode; no simulated fill was created."

        if quote_age < 0 or quote_age > resolved_policy.maximum_quote_age_seconds:
            status = SimulationStatus.REJECTED
            reason = f"Quote age {quote_age:.3f}s exceeded the stale-data policy."
        elif spread_points > resolved_policy.maximum_spread_points:
            status = SimulationStatus.REJECTED
            reason = f"Spread {spread_points:.3f} points exceeded the configured limit."
        elif requested_units > resolved_limits.maximum_position_units:
            status = SimulationStatus.REJECTED
            reason = "Requested units exceeded the immutable position-size limit."
        elif mode is SimulationMode.PAPER and signal is not PositionSignal.FLAT:
            status = SimulationStatus.FILLED
            slippage = resolved_policy.slippage_points * resolved_policy.point_size
            fill_price = (
                quote.ask + slippage
                if signal is PositionSignal.LONG
                else quote.bid - slippage
            )
            reason = "Deterministic paper fill recorded after risk and quote checks."

        decision_id = self._next_decision_id()
        decision = SimulationDecision(
            decision_id=decision_id,
            mode=mode,
            status=status,
            pair=pair,
            timeframe=timeframe,
            strategy_version_id=strategy_version_id,
            signal=signal,
            requested_units=requested_units,
            quote=quote,
            spread_points=spread_points,
            simulated_fill_price=fill_price,
            reason=reason,
            created_at=now,
        )

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO simulation_decisions(decision_id, payload, created_at) "
                "VALUES (?, ?, ?)",
                (decision.decision_id, decision.model_dump_json(), now.isoformat()),
            )

        return decision

    def all_decisions(self) -> tuple[SimulationDecision, ...]:
        """Return every observation, rejection, and paper fill in order."""

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM simulation_decisions "
                "ORDER BY created_at, decision_id",
            ).fetchall()

        return tuple(SimulationDecision.model_validate_json(row[0]) for row in rows)

    def _next_decision_id(self) -> str:
        """Generate a sequential identifier without reusing deleted numbers."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM simulation_decisions",
            ).fetchone()

        count = int(row[0]) if row is not None else 0

        return f"decision_{count + 1:09d}"

    def _initialize(self) -> None:
        """Create the append-only simulation schema."""

        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS simulation_decisions (
                    decision_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a short serialized ledger transaction."""

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
