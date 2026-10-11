from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.agents import AgentTask
from ai_quant_lab.backtesting import BacktestResult
from ai_quant_lab.data.catalog import DatasetManifest
from ai_quant_lab.regimes import RegimeSummary
from ai_quant_lab.validation import (
    MonteCarloSummary,
    ParameterStabilitySummary,
    ValidationReport,
    WalkForwardSummary,
)


class ResearchReport(BaseModel):
    """Complete, serializable audit record for one research experiment."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    experiment_id: str = Field(min_length=1)
    strategy_version_id: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dataset: DatasetManifest
    backtest: BacktestResult
    regimes: RegimeSummary
    validation: ValidationReport
    monte_carlo: MonteCarloSummary | None = None
    walk_forward: WalkForwardSummary | None = None
    parameter_stability: ParameterStabilitySummary | None = None
    agent_tasks: tuple[AgentTask, ...] = ()
    safety_notice: str = (
        "Research result only. It is not approved for real-money live trading."
    )


class WrittenResearchReport(BaseModel):
    """Paths of the durable JSON and Markdown report artifacts."""

    model_config = ConfigDict(frozen=True)

    json_path: Path
    markdown_path: Path


def write_research_report(
    report: ResearchReport,
    output_root: str | Path = "data/experiments",
) -> WrittenResearchReport:
    """Atomically persist machine-readable and human-readable reports."""

    experiment_dir = Path(output_root) / report.experiment_id
    experiment_dir.mkdir(parents=True, exist_ok=True)

    json_path = experiment_dir / "report.json"
    markdown_path = experiment_dir / "report.md"

    _atomic_write_text(
        json_path,
        report.model_dump_json(indent=2),
    )
    _atomic_write_text(
        markdown_path,
        _render_markdown(report),
    )

    return WrittenResearchReport(
        json_path=json_path,
        markdown_path=markdown_path,
    )


def _render_markdown(report: ResearchReport) -> str:
    """Render one concise report for a human reviewer."""

    metrics = report.backtest.metrics
    checks = "\n".join(
        f"- {check.name}: **{check.status.value}** — {check.detail}"
        for check in report.validation.checks
    )
    tasks = "\n".join(
        f"- `{task.task_id}` {task.title}: {task.status.value}"
        for task in report.agent_tasks
    )
    monte_carlo = (
        (
            f"- Probability of profit: {report.monte_carlo.probability_of_profit:.1%}\n"
            f"- 5th percentile: {report.monte_carlo.fifth_percentile_profit:.2f}\n"
            f"- Median: {report.monte_carlo.median_profit:.2f}\n"
            f"- 95th percentile: {report.monte_carlo.ninety_fifth_percentile_profit:.2f}"
        )
        if report.monte_carlo is not None
        else "- Not available because the backtest produced no closed trades."
    )
    walk_forward = (
        (
            f"- Windows: {len(report.walk_forward.windows)}\n"
            f"- Pass fraction: {report.walk_forward.pass_fraction:.1%}\n"
            f"- Passed: {report.walk_forward.passed}"
        )
        if report.walk_forward is not None
        else "- Not available for this dataset."
    )
    parameter_stability = (
        (
            f"- Variants: {len(report.parameter_stability.variants)}\n"
            f"- Profitable fraction: "
            f"{report.parameter_stability.profitable_fraction:.1%}\n"
            f"- Return range: "
            f"{report.parameter_stability.return_range_percent:.2f}%\n"
            f"- Passed: {report.parameter_stability.passed}"
        )
        if report.parameter_stability is not None
        else "- Not available."
    )

    return (
        f"# AI Quant Lab Research Report\n\n"
        f"Experiment: `{report.experiment_id}`  \n"
        f"Strategy version: `{report.strategy_version_id}`  \n"
        f"Generated: {report.generated_at.isoformat()}  \n"
        f"Safety: **{report.safety_notice}**\n\n"
        f"## Dataset\n\n"
        f"- Pair / timeframe: {report.dataset.pair} / {report.dataset.timeframe}\n"
        f"- Bars: {report.dataset.bar_count}\n"
        f"- SHA-256: `{report.dataset.sha256}`\n"
        f"- Range: {report.dataset.first_timestamp.isoformat()} to "
        f"{report.dataset.last_timestamp.isoformat()}\n\n"
        f"## Strategy and Backtest\n\n"
        f"- Strategy: `{report.backtest.strategy.name}`\n"
        f"- Net profit: {metrics.net_profit:.2f}\n"
        f"- Net return: {metrics.net_return_percent:.2f}%\n"
        f"- Maximum drawdown: {metrics.maximum_drawdown_percent:.2f}%\n"
        f"- Sharpe ratio: {metrics.sharpe_ratio:.3f}\n"
        f"- Sortino ratio: {metrics.sortino_ratio:.3f}\n"
        f"- Profit factor: {metrics.profit_factor:.3f}\n"
        f"- Trades: {metrics.trade_count}\n"
        f"- Win rate: {metrics.win_rate_percent:.2f}%\n\n"
        f"## Market Regimes\n\n"
        f"- Dominant: `{report.regimes.dominant_regime.value}`\n"
        f"- Latest: `{report.regimes.latest_regime.value}`\n\n"
        f"## Validation Gates\n\n{checks}\n\n"
        f"Quantitative gates passed: "
        f"**{report.validation.passed_quantitative_gates}**  \n"
        f"Eligible for live trading: **False**\n\n"
        f"## Monte Carlo\n\n{monte_carlo}\n\n"
        f"## Walk-Forward\n\n{walk_forward}\n\n"
        f"## Parameter Stability\n\n{parameter_stability}\n\n"
        f"## Agent Audit Trail\n\n{tasks}\n"
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text through a sibling temporary file and atomic rename."""

    temporary_path = path.with_suffix(path.suffix + ".temporary")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)
