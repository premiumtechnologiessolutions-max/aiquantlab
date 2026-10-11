from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents.identifiers import normalize_identifier
from ai_quant_lab.backtesting import BacktestConfig, BacktestResult, run_backtest
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import build_dataset_manifest, write_dataset_manifest
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.strategies import ResearchStrategy
from ai_quant_lab.validation.gates import (
    CheckStatus,
    ValidationCheck,
    ValidationPolicy,
    ValidationReport,
    validate_backtest,
)


class BlindDatasetEntry(BaseModel):
    """Metadata exposed for a sealed holdout without exposing bar contents."""

    model_config = ConfigDict(frozen=True)

    vault_id: str
    pair: ForexPair
    timeframe: Timeframe
    bar_count: int = Field(ge=2)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sealed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BlindValidationResult(BaseModel):
    """Independent holdout result returned by the authorized validation service."""

    model_config = ConfigDict(frozen=True)

    vault_entry: BlindDatasetEntry
    backtest: BacktestResult
    validation: ValidationReport
    requester_key: str


class BlindValidationVault:
    """Filesystem holdout boundary readable only through an allow-listed service."""

    def __init__(
        self,
        root: str | Path = "data/blind_validation",
        *,
        authorized_agent_keys: tuple[str, ...] = ("sentinel",),
    ) -> None:
        self.root = Path(root)
        self.authorized_agent_keys = frozenset(
            normalize_identifier(key, field_name="Authorized agent key")
            for key in authorized_agent_keys
        )

        if not self.authorized_agent_keys:
            raise ValueError("Blind validation requires at least one authorized agent.")

    def seal(
        self,
        *,
        vault_id: str,
        bars: Sequence[MarketBar],
    ) -> BlindDatasetEntry:
        """Seal an immutable holdout dataset and its checksum."""

        normalized_id = normalize_identifier(vault_id, field_name="Vault ID")

        if len(bars) < 2:
            raise ValueError("A blind holdout requires at least two bars.")

        vault_root = self.root / normalized_id

        if vault_root.exists():
            raise FileExistsError(f"Blind vault '{normalized_id}' is already sealed.")

        store = ParquetMarketStore(vault_root)
        store.write_bars(bars)
        manifest = build_dataset_manifest(store, bars[0].pair, bars[0].timeframe)
        write_dataset_manifest(manifest, vault_root)
        entry = BlindDatasetEntry(
            vault_id=normalized_id,
            pair=manifest.pair,
            timeframe=manifest.timeframe,
            bar_count=manifest.bar_count,
            dataset_sha256=manifest.sha256,
        )
        entry_path = vault_root / "entry.json"
        entry_path.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

        return entry

    def entry(self, vault_id: str) -> BlindDatasetEntry:
        """Return safe holdout metadata without reading sealed market bars."""

        normalized_id = normalize_identifier(vault_id, field_name="Vault ID")
        path = self.root / normalized_id / "entry.json"

        if not path.exists():
            raise KeyError(f"Blind vault '{normalized_id}' does not exist.")

        return BlindDatasetEntry.model_validate_json(path.read_text(encoding="utf-8"))

    def open_for_validation(
        self,
        vault_id: str,
        *,
        requester_key: str,
    ) -> list[MarketBar]:
        """Read holdout bars only for a configured independent validator."""

        normalized_requester = normalize_identifier(
            requester_key,
            field_name="Requester key",
        )

        if normalized_requester not in self.authorized_agent_keys:
            raise PermissionError(
                f"Agent '{normalized_requester}' cannot access blind holdout data.",
            )

        entry = self.entry(vault_id)
        store = ParquetMarketStore(self.root / entry.vault_id)

        return store.read_bars(entry.pair, entry.timeframe)


def run_blind_validation(
    *,
    vault: BlindValidationVault,
    vault_id: str,
    requester_key: str,
    strategy: ResearchStrategy,
    backtest_config: BacktestConfig | None = None,
    validation_policy: ValidationPolicy | None = None,
) -> BlindValidationResult:
    """Run an authorized OOS backtest and label the evidence explicitly."""

    entry = vault.entry(vault_id)
    bars = vault.open_for_validation(vault_id, requester_key=requester_key)
    result = run_backtest(bars, strategy, backtest_config)
    base_validation = validate_backtest(result, validation_policy)
    oos_check = ValidationCheck(
        name="out_of_sample",
        status=(
            CheckStatus.PASSED
            if base_validation.passed_quantitative_gates
            else CheckStatus.FAILED
        ),
        detail=(
            f"Blind holdout '{entry.vault_id}' ({entry.dataset_sha256[:12]}...) "
            "was opened only by the authorized validation service."
        ),
    )
    validation = validate_backtest(
        result,
        validation_policy,
        stage_evidence=(oos_check,),
    )

    return BlindValidationResult(
        vault_entry=entry,
        backtest=result,
        validation=validation,
        requester_key=requester_key,
    )
