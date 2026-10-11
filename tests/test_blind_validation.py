from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.strategies import BuyAndHold
from ai_quant_lab.validation import (
    BlindValidationVault,
    CheckStatus,
    ValidationPolicy,
    run_blind_validation,
)


def make_holdout(count: int = 30) -> list[MarketBar]:
    """Create a controlled holdout that is never used for strategy fitting."""

    start = datetime(2026, 9, 1, tzinfo=UTC)

    return [
        MarketBar(
            pair="EURUSD",
            timeframe="M15",
            timestamp=start + timedelta(minutes=15 * index),
            open=1.10 + index * 0.0005,
            high=1.101 + index * 0.0005,
            low=1.099 + index * 0.0005,
            close=1.1005 + index * 0.0005,
            tick_volume=100,
            spread_points=1,
        )
        for index in range(count)
    ]


def test_blind_vault_allows_only_independent_validator(
    tmp_path: Path,
) -> None:
    vault = BlindValidationVault(tmp_path / "vault")
    entry = vault.seal(vault_id="eurusd_final_holdout", bars=make_holdout())

    assert entry.bar_count == 30
    assert vault.entry(entry.vault_id) == entry

    with pytest.raises(PermissionError, match="cannot access"):
        vault.open_for_validation(entry.vault_id, requester_key="nova")

    assert len(
        vault.open_for_validation(entry.vault_id, requester_key="sentinel")
    ) == 30

    with pytest.raises(FileExistsError, match="already sealed"):
        vault.seal(vault_id=entry.vault_id, bars=make_holdout())


def test_sentinel_records_real_out_of_sample_evidence(
    tmp_path: Path,
) -> None:
    vault = BlindValidationVault(tmp_path / "vault")
    entry = vault.seal(vault_id="holdout_1", bars=make_holdout())
    result = run_blind_validation(
        vault=vault,
        vault_id=entry.vault_id,
        requester_key="sentinel",
        strategy=BuyAndHold(),
        validation_policy=ValidationPolicy(
            minimum_trades=1,
            minimum_profit_factor=0,
            minimum_sharpe_ratio=-100,
            maximum_drawdown_percent=100,
        ),
    )

    oos = next(
        check
        for check in result.validation.checks
        if check.name == "out_of_sample"
    )

    assert oos.status is CheckStatus.PASSED
    assert result.requester_key == "sentinel"
    assert result.backtest.started_at == make_holdout()[0].timestamp
