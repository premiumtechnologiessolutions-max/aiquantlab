from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_quant_lab.risk import RiskLimits
from ai_quant_lab.simulation import (
    MarketQuote,
    SimulationLedger,
    SimulationMode,
    SimulationPolicy,
    SimulationStatus,
)
from ai_quant_lab.strategies import PositionSignal


def test_shadow_records_signal_without_fill(tmp_path: Path) -> None:
    ledger = SimulationLedger(tmp_path / "shadow.sqlite3")
    now = datetime.now(UTC)
    decision = ledger.submit(
        mode=SimulationMode.SHADOW,
        pair="EURUSD",
        timeframe="M15",
        strategy_version_id="strategy_1",
        signal=PositionSignal.LONG,
        requested_units=10_000,
        quote=MarketQuote(timestamp=now, bid=1.1000, ask=1.1001),
        observed_at=now,
    )

    assert decision.status is SimulationStatus.OBSERVED
    assert decision.simulated_fill_price is None
    assert ledger.all_decisions() == (decision,)


def test_paper_fill_includes_ask_and_slippage(tmp_path: Path) -> None:
    ledger = SimulationLedger(tmp_path / "paper.sqlite3")
    now = datetime.now(UTC)
    decision = ledger.submit(
        mode=SimulationMode.PAPER,
        pair="EURUSD",
        timeframe="M15",
        strategy_version_id="strategy_1",
        signal=PositionSignal.LONG,
        requested_units=10_000,
        quote=MarketQuote(timestamp=now, bid=1.1000, ask=1.1001),
        policy=SimulationPolicy(slippage_points=2),
        observed_at=now,
    )

    assert decision.status is SimulationStatus.FILLED
    assert decision.simulated_fill_price == 1.10012


def test_simulation_rejects_stale_quotes_spread_and_position_limit(
    tmp_path: Path,
) -> None:
    ledger = SimulationLedger(tmp_path / "rejections.sqlite3")
    now = datetime.now(UTC)
    stale = ledger.submit(
        mode=SimulationMode.PAPER,
        pair="EURUSD",
        timeframe="M15",
        strategy_version_id="strategy_1",
        signal=PositionSignal.SHORT,
        requested_units=10_000,
        quote=MarketQuote(
            timestamp=now - timedelta(minutes=1),
            bid=1.1000,
            ask=1.1001,
        ),
        observed_at=now,
    )
    wide = ledger.submit(
        mode=SimulationMode.PAPER,
        pair="EURUSD",
        timeframe="M15",
        strategy_version_id="strategy_1",
        signal=PositionSignal.SHORT,
        requested_units=10_000,
        quote=MarketQuote(timestamp=now, bid=1.1000, ask=1.1010),
        observed_at=now,
    )
    oversized = ledger.submit(
        mode=SimulationMode.PAPER,
        pair="EURUSD",
        timeframe="M15",
        strategy_version_id="strategy_1",
        signal=PositionSignal.SHORT,
        requested_units=20_000,
        quote=MarketQuote(timestamp=now, bid=1.1000, ask=1.1001),
        risk_limits=RiskLimits(maximum_position_units=10_000),
        observed_at=now,
    )

    assert stale.status is SimulationStatus.REJECTED
    assert "Quote age" in stale.reason
    assert wide.status is SimulationStatus.REJECTED
    assert "Spread" in wide.reason
    assert oversized.status is SimulationStatus.REJECTED
    assert "position-size" in oversized.reason
    assert len(ledger.all_decisions()) == 3
