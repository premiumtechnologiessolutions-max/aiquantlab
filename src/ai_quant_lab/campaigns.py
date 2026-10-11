from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import BacktestConfig, BacktestMetrics
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.research import ResearchRunResult, run_research_experiment
from ai_quant_lab.strategies import SUPPORTED_STRATEGIES, StrategyName, normalize_strategy_name
from ai_quant_lab.validation import CheckStatus, ValidationPolicy


class CampaignEntry(BaseModel):
    """One ranked strategy result inside a reproducible research campaign."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    strategy_name: StrategyName
    experiment_id: str
    strategy_version_id: str
    metrics: BacktestMetrics
    quantitative_gates_passed: bool
    robustness_checks_passed: int = Field(ge=0)
    report_path: Path


class ResearchCampaignResult(BaseModel):
    """Persisted comparison of multiple strategies on one identical dataset."""

    model_config = ConfigDict(frozen=True)

    campaign_id: str
    pair: ForexPair
    timeframe: Timeframe
    generated_at: datetime
    research_leader: StrategyName | None
    entries: tuple[CampaignEntry, ...]
    json_path: Path
    markdown_path: Path
    live_trading_eligible: bool = False


def run_research_campaign(
    *,
    pair: ForexPair,
    timeframe: Timeframe,
    strategy_names: Sequence[str] = SUPPORTED_STRATEGIES,
    data_root: str | Path = "data/processed",
    experiment_root: str | Path = "data/experiments",
    campaign_root: str | Path = "data/campaigns",
    backtest_config: BacktestConfig | None = None,
    validation_policy: ValidationPolicy | None = None,
    build_id: str = "local_build",
) -> ResearchCampaignResult:
    """Run and rank a declared strategy set without auto-promoting any result."""

    normalized = tuple(normalize_strategy_name(name) for name in strategy_names)

    if not normalized:
        raise ValueError("A research campaign requires at least one strategy.")

    if len(normalized) != len(set(normalized)):
        raise ValueError("Research campaign strategy names must be unique.")

    runs = tuple(
        run_research_experiment(
            pair=pair,
            timeframe=timeframe,
            data_root=data_root,
            output_root=experiment_root,
            strategy_name=name,
            backtest_config=backtest_config,
            validation_policy=validation_policy,
            build_id=build_id,
        )
        for name in normalized
    )
    ordered = sorted(
        zip(normalized, runs, strict=True),
        key=lambda item: _ranking_key(item[1]),
        reverse=True,
    )
    entries = tuple(
        _campaign_entry(rank, name, run)
        for rank, (name, run) in enumerate(ordered, start=1)
    )
    generated_at = datetime.now(UTC)
    campaign_id = f"campaign_{generated_at:%Y%m%dT%H%M%S%fZ}_{pair}_{timeframe}".lower()
    root = Path(campaign_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{campaign_id}.json"
    markdown_path = root / f"{campaign_id}.md"
    leader = entries[0].strategy_name if entries else None
    result = ResearchCampaignResult(
        campaign_id=campaign_id,
        pair=pair,
        timeframe=timeframe,
        generated_at=generated_at,
        research_leader=leader,
        entries=entries,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    _atomic_write(json_path, result.model_dump_json(indent=2))
    _atomic_write(markdown_path, _render_markdown(result))

    return result


def latest_campaign(
    root: str | Path = "data/campaigns",
) -> ResearchCampaignResult | None:
    """Load the most recently written campaign summary when one exists."""

    paths = sorted(Path(root).glob("campaign_*.json"), reverse=True)

    if not paths:
        return None

    return ResearchCampaignResult.model_validate_json(paths[0].read_text(encoding="utf-8"))


def _campaign_entry(
    rank: int,
    name: StrategyName,
    run: ResearchRunResult,
) -> CampaignEntry:
    robustness_names = {"monte_carlo", "walk_forward", "parameter_stability"}
    robustness_passes = sum(
        check.name in robustness_names and check.status is CheckStatus.PASSED
        for check in run.validation.checks
    )

    return CampaignEntry(
        rank=rank,
        strategy_name=name,
        experiment_id=run.experiment_id,
        strategy_version_id=run.strategy_version_id,
        metrics=run.backtest.metrics,
        quantitative_gates_passed=run.validation.passed_quantitative_gates,
        robustness_checks_passed=robustness_passes,
        report_path=run.markdown_report_path,
    )


def _ranking_key(run: ResearchRunResult) -> tuple[int, int, float, float, int]:
    robustness_names = {"monte_carlo", "walk_forward", "parameter_stability"}
    robustness_passes = sum(
        check.name in robustness_names and check.status is CheckStatus.PASSED
        for check in run.validation.checks
    )
    metrics = run.backtest.metrics

    return (
        int(run.validation.passed_quantitative_gates),
        robustness_passes,
        metrics.net_return_percent,
        -metrics.maximum_drawdown_percent,
        metrics.trade_count,
    )


def _render_markdown(result: ResearchCampaignResult) -> str:
    rows = [
        f"# Research Campaign — {result.pair} {result.timeframe}",
        "",
        f"Campaign ID: `{result.campaign_id}`",
        f"Research leader: `{result.research_leader or 'none'}`",
        "",
        "> Ranking is research evidence only. It does not authorize live trading.",
        "",
        "| Rank | Strategy | Gates | Robustness | Return % | Drawdown % | Trades |",
        "|---:|---|:---:|---:|---:|---:|---:|",
    ]
    rows.extend(
        (
            f"| {entry.rank} | {entry.strategy_name} | "
            f"{'pass' if entry.quantitative_gates_passed else 'fail'} | "
            f"{entry.robustness_checks_passed}/3 | "
            f"{entry.metrics.net_return_percent:.3f} | "
            f"{entry.metrics.maximum_drawdown_percent:.3f} | "
            f"{entry.metrics.trade_count} |"
        )
        for entry in result.entries
    )
    rows.extend(("", "Live trading eligible: **False**", ""))

    return "\n".join(rows)


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".temporary")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
