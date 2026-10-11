from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai_quant_lab.broker import DemoAccountSnapshot, DemoQuoteSnapshot
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.regimes import MarketRegime, detect_market_regimes
from ai_quant_lab.simulation import (
    MarketQuote,
    SimulationDecision,
    SimulationLedger,
    SimulationMode,
)
from ai_quant_lab.strategies import (
    STRATEGY_CATALOG,
    SUPPORTED_STRATEGIES,
    PositionSignal,
    StrategyFamily,
    StrategyName,
    build_strategy,
)


class DemoMarketGateway(Protocol):
    """Market-data methods consumed by the continuous demo monitor."""

    def connect(self) -> DemoAccountSnapshot: ...

    def latest_quote(self, pair: ForexPair) -> DemoQuoteSnapshot: ...

    def recent_bars(
        self,
        pair: ForexPair,
        timeframe: Timeframe,
        *,
        count: int = 300,
    ) -> tuple[MarketBar, ...]: ...


class MonitorConfig(BaseModel):
    """Bounded settings for one recurring MT5 demo market scan."""

    model_config = ConfigDict(frozen=True)

    pairs: tuple[ForexPair, ...] = ("EURUSD",)
    timeframe: Timeframe = "M15"
    strategy_names: tuple[StrategyName, ...] = tuple(
        name for name in SUPPORTED_STRATEGIES if name != "buy_and_hold"
    )
    lookback_bars: int = Field(default=300, ge=60, le=10_000)
    regime_window: int = Field(default=30, ge=3, le=1_000)
    minimum_agreement: int = Field(default=2, ge=1)
    mode: SimulationMode = SimulationMode.SHADOW
    requested_units: float = Field(default=10_000.0, gt=0)

    @model_validator(mode="after")
    def validate_strategy_set(self) -> MonitorConfig:
        """Reject empty, duplicate, or impossible ensemble settings."""

        if not self.strategy_names:
            raise ValueError("The market monitor requires at least one strategy.")

        if len(self.strategy_names) != len(set(self.strategy_names)):
            raise ValueError("Market monitor strategy names must be unique.")

        if self.minimum_agreement > len(self.strategy_names) * 2:
            raise ValueError("Minimum agreement is impossible for the selected strategy set.")

        return self


class StrategySignalSnapshot(BaseModel):
    """Latest causal signal emitted by one strategy during a market scan."""

    model_config = ConfigDict(frozen=True)

    strategy_name: StrategyName
    family: StrategyFamily
    signal: PositionSignal
    regime_weight: int = Field(ge=1, le=2)


class MarketScanResult(BaseModel):
    """Persisted ensemble observation from a live MT5 demo quote and bars."""

    model_config = ConfigDict(frozen=True)

    scan_id: str
    pair: ForexPair
    timeframe: Timeframe
    observed_at: datetime
    latest_bar_at: datetime
    quote: DemoQuoteSnapshot
    regime: MarketRegime
    strategy_signals: tuple[StrategySignalSnapshot, ...]
    long_votes: int = Field(ge=0)
    short_votes: int = Field(ge=0)
    consensus: PositionSignal
    simulation: SimulationDecision


class MonitorStore:
    """Append-only scan history used by agents and the voice dashboard."""

    def __init__(self, path: str | Path = "data/monitor/scans.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def append(self, scan: MarketScanResult) -> None:
        """Persist one immutable scan."""

        with self._connection() as connection:
            connection.execute(
                "INSERT INTO market_scans(scan_id, pair, payload, created_at) VALUES (?, ?, ?, ?)",
                (scan.scan_id, scan.pair, scan.model_dump_json(), scan.observed_at.isoformat()),
            )

    def latest(self, pair: ForexPair | None = None) -> MarketScanResult | None:
        """Return the newest scan globally or for one pair."""

        with self._connection() as connection:
            if pair is None:
                row = connection.execute(
                    "SELECT payload FROM market_scans ORDER BY created_at DESC, scan_id DESC LIMIT 1"
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload FROM market_scans WHERE pair = ? "
                    "ORDER BY created_at DESC, scan_id DESC LIMIT 1",
                    (pair,),
                ).fetchone()

        return MarketScanResult.model_validate_json(row[0]) if row is not None else None

    def recent(self, limit: int = 100) -> tuple[MarketScanResult, ...]:
        """Return recent scans newest first."""

        if limit < 1 or limit > 1_000:
            raise ValueError("Monitor scan limit must be between one and one thousand.")

        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM market_scans ORDER BY created_at DESC, scan_id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return tuple(MarketScanResult.model_validate_json(row[0]) for row in rows)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS market_scans (
                    scan_id TEXT PRIMARY KEY,
                    pair TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_market_scans_pair_time
                    ON market_scans(pair, created_at);
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
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


class DemoMarketMonitor:
    """Continuously observable ensemble that never auto-sends broker orders."""

    def __init__(
        self,
        gateway: DemoMarketGateway,
        config: MonitorConfig | None = None,
        *,
        simulation_ledger: SimulationLedger | None = None,
        store: MonitorStore | None = None,
    ) -> None:
        self.gateway = gateway
        self.config = config or MonitorConfig()
        self.simulation_ledger = simulation_ledger or SimulationLedger(
            "data/simulation/monitor.sqlite3"
        )
        self.store = store or MonitorStore()
        self._lock = RLock()
        strategy_key = ",".join(self.config.strategy_names).encode()
        self.strategy_version_id = f"ensemble_{hashlib.sha256(strategy_key).hexdigest()[:16]}"

    def scan_once(self) -> tuple[MarketScanResult, ...]:
        """Read completed bars and quotes, then append shadow or paper decisions."""

        with self._lock:
            self.gateway.connect()

            return tuple(self._scan_pair(pair) for pair in self.config.pairs)

    def _scan_pair(self, pair: ForexPair) -> MarketScanResult:
        bars = self.gateway.recent_bars(
            pair,
            self.config.timeframe,
            count=self.config.lookback_bars,
        )

        if len(bars) < self.config.regime_window:
            raise RuntimeError(
                f"MT5 returned {len(bars)} completed bars for {pair}; "
                f"at least {self.config.regime_window} are required."
            )

        quote = self.gateway.latest_quote(pair)
        regimes = detect_market_regimes(bars, window=self.config.regime_window)
        snapshots = tuple(
            self._strategy_signal(name, bars, regimes.latest_regime)
            for name in self.config.strategy_names
        )
        long_votes = sum(
            snapshot.regime_weight
            for snapshot in snapshots
            if snapshot.signal is PositionSignal.LONG
        )
        short_votes = sum(
            snapshot.regime_weight
            for snapshot in snapshots
            if snapshot.signal is PositionSignal.SHORT
        )
        consensus = _consensus(
            long_votes=long_votes,
            short_votes=short_votes,
            minimum_agreement=self.config.minimum_agreement,
        )
        observed_at = datetime.now(UTC)
        simulation = self.simulation_ledger.submit(
            mode=self.config.mode,
            pair=pair,
            timeframe=self.config.timeframe,
            strategy_version_id=self.strategy_version_id,
            signal=consensus,
            requested_units=self.config.requested_units,
            quote=MarketQuote(
                timestamp=quote.timestamp,
                bid=quote.bid,
                ask=quote.ask,
            ),
            observed_at=observed_at,
        )
        scan_key = (
            f"{pair}|{self.config.timeframe}|{bars[-1].timestamp.isoformat()}|"
            f"{quote.timestamp.isoformat()}"
        ).encode()
        scan = MarketScanResult(
            scan_id=f"scan_{hashlib.sha256(scan_key).hexdigest()[:24]}",
            pair=pair,
            timeframe=self.config.timeframe,
            observed_at=observed_at,
            latest_bar_at=bars[-1].timestamp,
            quote=quote,
            regime=regimes.latest_regime,
            strategy_signals=snapshots,
            long_votes=long_votes,
            short_votes=short_votes,
            consensus=consensus,
            simulation=simulation,
        )

        try:
            self.store.append(scan)
        except sqlite3.IntegrityError:
            existing = self.store.latest(pair)

            if existing is not None and existing.scan_id == scan.scan_id:
                return existing

            raise

        return scan

    @staticmethod
    def _strategy_signal(
        name: StrategyName,
        bars: tuple[MarketBar, ...],
        regime: MarketRegime,
    ) -> StrategySignalSnapshot:
        strategy = build_strategy(name)
        signals = strategy.generate_signals(bars)
        family = strategy.descriptor.family

        return StrategySignalSnapshot(
            strategy_name=name,
            family=family,
            signal=signals[-1],
            regime_weight=_regime_weight(family, regime),
        )


def _consensus(
    *,
    long_votes: int,
    short_votes: int,
    minimum_agreement: int,
) -> PositionSignal:
    if long_votes >= minimum_agreement and long_votes > short_votes:
        return PositionSignal.LONG

    if short_votes >= minimum_agreement and short_votes > long_votes:
        return PositionSignal.SHORT

    return PositionSignal.FLAT


def _regime_weight(family: StrategyFamily, regime: MarketRegime) -> int:
    trending_families = {
        StrategyFamily.TREND,
        StrategyFamily.MOMENTUM,
        StrategyFamily.BREAKOUT,
    }

    if regime in {MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN}:
        return 2 if family in trending_families | {StrategyFamily.ADAPTIVE} else 1

    if regime is MarketRegime.RANGING:
        return 2 if family in {StrategyFamily.MEAN_REVERSION, StrategyFamily.STATISTICAL} else 1

    if regime is MarketRegime.HIGH_VOLATILITY:
        return (
            2
            if family
            in {
                StrategyFamily.VOLATILITY,
                StrategyFamily.BREAKOUT,
                StrategyFamily.ADAPTIVE,
            }
            else 1
        )

    return 1


def strategy_catalog_payload() -> tuple[dict[str, object], ...]:
    """Return JSON-safe strategy metadata for the local voice dashboard."""

    return tuple(specification.model_dump(mode="json") for specification in STRATEGY_CATALOG)
