from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ai_quant_lab.agents import AtlasCoordinator, TaskPriority, create_default_agent_team
from ai_quant_lab.backtesting import BacktestConfig, BacktestResult, run_backtest
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.catalog import build_dataset_manifest
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.experiments import ExperimentRecord, ExperimentRegistry
from ai_quant_lab.intelligence import (
    PairIntelligenceProfile,
    PairIntelligenceStore,
    StrategyEvidence,
)
from ai_quant_lab.regimes import RegimeSummary, detect_market_regimes
from ai_quant_lab.reporting import ResearchReport, write_research_report
from ai_quant_lab.risk import assert_safe_mode
from ai_quant_lab.strategies import (
    ResearchStrategy,
    StrategyName,
    build_strategy,
    neighboring_variants,
)
from ai_quant_lab.validation import (
    CheckStatus,
    MonteCarloSummary,
    ParameterStabilitySummary,
    ValidationCheck,
    ValidationPolicy,
    ValidationReport,
    WalkForwardSummary,
    assess_parameter_stability,
    monte_carlo_trade_profits,
    run_walk_forward_validation,
    validate_backtest,
)


class ResearchRunResult(BaseModel):
    """Artifacts and headline results produced by one complete research run."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    strategy_version_id: str
    backtest: BacktestResult
    regimes: RegimeSummary
    validation: ValidationReport
    monte_carlo: MonteCarloSummary | None
    walk_forward: WalkForwardSummary | None
    parameter_stability: ParameterStabilitySummary
    json_report_path: Path
    markdown_report_path: Path
    intelligence_profile_path: Path


def run_research_experiment(
    *,
    pair: ForexPair,
    timeframe: Timeframe,
    data_root: str | Path = "data/processed",
    output_root: str | Path = "data/experiments",
    intelligence_root: str | Path | None = None,
    strategy_name: StrategyName = "moving_average_crossover",
    fast_window: int = 20,
    slow_window: int = 50,
    mean_reversion_window: int = 30,
    entry_z: float = 1.5,
    exit_z: float = 0.25,
    regime_window: int = 30,
    backtest_config: BacktestConfig | None = None,
    validation_policy: ValidationPolicy | None = None,
    mode: str = "research",
    build_id: str = "local_build",
    strategy_parameters: Mapping[str, int | float | str] | None = None,
) -> ResearchRunResult:
    """Execute the full safe MVP pipeline and persist an auditable report."""

    assert_safe_mode(mode)
    store = ParquetMarketStore(data_root)
    team = create_default_agent_team()
    coordinator = AtlasCoordinator(team)

    root_task = coordinator.delegate(
        agent_key="atlas",
        title=f"Research {pair} {timeframe}",
        description="Coordinate one complete, reproducible research experiment.",
        priority=TaskPriority.HIGH,
        tags=("research", pair.casefold(), timeframe.casefold()),
    )
    atlas = team.get_agent("atlas")
    atlas.start_assigned_task(root_task.task_id)

    data_task = coordinator.delegate(
        agent_key="vega",
        title="Load and fingerprint the canonical dataset",
        parent_task_id=root_task.task_id,
    )
    vega = team.get_agent("vega")
    vega.start_assigned_task(data_task.task_id)
    bars = store.read_bars(pair, timeframe)
    manifest = build_dataset_manifest(store, pair, timeframe)
    vega.complete_task(message=f"Validated {len(bars)} bars; SHA-256 {manifest.sha256}.")

    regime_task = coordinator.delegate(
        agent_key="iris",
        title="Detect trailing market regimes",
        parent_task_id=root_task.task_id,
    )
    iris = team.get_agent("iris")
    iris.start_assigned_task(regime_task.task_id)
    regimes = detect_market_regimes(bars, window=regime_window)
    iris.complete_task(message=f"Dominant regime: {regimes.dominant_regime.value}.")

    strategy = _build_strategy(
        strategy_name=strategy_name,
        fast_window=fast_window,
        slow_window=slow_window,
        mean_reversion_window=mean_reversion_window,
        entry_z=entry_z,
        exit_z=exit_z,
        strategy_parameters=strategy_parameters,
    )

    backtest_task = coordinator.delegate(
        agent_key="chronos",
        title=f"Backtest {strategy.descriptor.name} with execution costs",
        parent_task_id=root_task.task_id,
    )
    chronos = team.get_agent("chronos")
    chronos.start_assigned_task(backtest_task.task_id)
    backtest = run_backtest(bars, strategy, backtest_config)
    chronos.complete_task(
        message=(
            f"Completed {backtest.metrics.trade_count} trades; net result "
            f"{backtest.metrics.net_profit:.2f}."
        )
    )

    validation_task = coordinator.delegate(
        agent_key="sentinel",
        title="Apply independent validation and robustness gates",
        parent_task_id=root_task.task_id,
    )
    sentinel = team.get_agent("sentinel")
    sentinel.start_assigned_task(validation_task.task_id)
    monte_carlo = monte_carlo_trade_profits(backtest.trades) if backtest.trades else None
    resolved_policy = validation_policy or ValidationPolicy()
    stage_evidence: list[ValidationCheck] = [
        ValidationCheck(
            name="monte_carlo",
            status=(
                CheckStatus.PASSED
                if monte_carlo is not None and monte_carlo.probability_of_profit >= 0.5
                else CheckStatus.FAILED
            ),
            detail=(
                (f"Bootstrapped probability of profit was {monte_carlo.probability_of_profit:.1%}.")
                if monte_carlo is not None
                else "No closed trades were available for Monte Carlo analysis."
            ),
        )
    ]
    walk_forward: WalkForwardSummary | None = None

    try:
        walk_forward = run_walk_forward_validation(
            bars,
            strategy_factory=lambda: _build_strategy(
                strategy_name=strategy_name,
                fast_window=fast_window,
                slow_window=slow_window,
                mean_reversion_window=mean_reversion_window,
                entry_z=entry_z,
                exit_z=exit_z,
                strategy_parameters=strategy_parameters,
            ),
            train_size=max(2, len(bars) // 2),
            test_size=max(2, len(bars) // 4),
            backtest_config=backtest_config,
            validation_policy=resolved_policy,
        )
    except ValueError as error:
        walk_forward_detail = f"Walk-forward could not run: {error}"
        walk_forward_status = CheckStatus.FAILED
    else:
        walk_forward_detail = (
            f"{len(walk_forward.windows)} purged chronological windows; "
            f"pass fraction {walk_forward.pass_fraction:.1%}."
        )
        walk_forward_status = CheckStatus.PASSED if walk_forward.passed else CheckStatus.FAILED

    stage_evidence.append(
        ValidationCheck(
            name="walk_forward",
            status=walk_forward_status,
            detail=walk_forward_detail,
        )
    )
    parameter_results = tuple(
        run_backtest(bars, variant, backtest_config)
        for variant in _parameter_variants(
            strategy_name=strategy_name,
            fast_window=fast_window,
            slow_window=slow_window,
            mean_reversion_window=mean_reversion_window,
            entry_z=entry_z,
            exit_z=exit_z,
            strategy_parameters=strategy_parameters,
        )
    )
    parameter_stability = assess_parameter_stability(parameter_results)
    stage_evidence.append(
        ValidationCheck(
            name="parameter_stability",
            status=(CheckStatus.PASSED if parameter_stability.passed else CheckStatus.FAILED),
            detail=(
                f"{len(parameter_stability.variants)} neighboring variants; "
                f"profitable fraction {parameter_stability.profitable_fraction:.1%}."
            ),
        )
    )
    validation = validate_backtest(
        backtest,
        resolved_policy,
        stage_evidence=tuple(stage_evidence),
    )
    sentinel.complete_task(
        message=(
            "Quantitative gates passed."
            if validation.passed_quantitative_gates
            else "Candidate failed one or more quantitative gates."
        )
    )

    report_task = coordinator.delegate(
        agent_key="echo",
        title="Prepare the human and machine-readable research report",
        parent_task_id=root_task.task_id,
    )
    echo = team.get_agent("echo")
    echo.start_assigned_task(report_task.task_id)
    echo.complete_task(message="Prepared the report payload and safety notice.")
    atlas.complete_task(message="Research pipeline and independent review completed.")

    generated_at = datetime.now(UTC)
    experiment_id = (
        f"{generated_at:%Y%m%dT%H%M%S%fZ}_"
        f"{pair}_{timeframe}_{strategy.descriptor.name}_"
        f"{manifest.sha256[:8]}"
    ).lower()
    registry = ExperimentRegistry(Path(output_root) / "registry.sqlite3")
    strategy_version = registry.register_strategy(
        descriptor=strategy.descriptor,
        code_commit=build_id,
    )
    report = ResearchReport(
        experiment_id=experiment_id,
        strategy_version_id=strategy_version.version_id,
        generated_at=generated_at,
        dataset=manifest,
        backtest=backtest,
        regimes=regimes,
        validation=validation,
        monte_carlo=monte_carlo,
        walk_forward=walk_forward,
        parameter_stability=parameter_stability,
        agent_tasks=team.task_board.all_tasks(),
    )
    written = write_research_report(report, output_root)
    registry.record_experiment(
        ExperimentRecord(
            experiment_id=experiment_id,
            strategy_version_id=strategy_version.version_id,
            pair=pair,
            timeframe=timeframe,
            dataset_sha256=manifest.sha256,
            metrics=backtest.metrics,
            validation=validation,
            json_report_path=str(written.json_path),
            markdown_report_path=str(written.markdown_path),
            created_at=generated_at,
        )
    )
    resolved_intelligence_root = (
        Path(intelligence_root)
        if intelligence_root is not None
        else Path(output_root).parent / "intelligence"
    )
    intelligence_profile = PairIntelligenceProfile(
        profile_id=f"profile_{experiment_id}",
        pair=pair,
        timeframe=timeframe,
        dataset_sha256=manifest.sha256,
        latest_regime=regimes.latest_regime,
        dominant_regime=regimes.dominant_regime,
        strategy_evidence=(
            StrategyEvidence(
                strategy_version_id=strategy_version.version_id,
                status=strategy_version.status,
                metrics=backtest.metrics,
                experiment_id=experiment_id,
                reason=(
                    "Basic quantitative gates passed; independent stages remain."
                    if validation.passed_quantitative_gates
                    else "One or more basic quantitative gates failed."
                ),
            ),
        ),
    )
    intelligence_path = PairIntelligenceStore(resolved_intelligence_root).write(
        intelligence_profile
    )

    return ResearchRunResult(
        experiment_id=experiment_id,
        strategy_version_id=strategy_version.version_id,
        backtest=backtest,
        regimes=regimes,
        validation=validation,
        monte_carlo=monte_carlo,
        walk_forward=walk_forward,
        parameter_stability=parameter_stability,
        json_report_path=written.json_path,
        markdown_report_path=written.markdown_path,
        intelligence_profile_path=intelligence_path,
    )


def _build_strategy(
    *,
    strategy_name: StrategyName,
    fast_window: int,
    slow_window: int,
    mean_reversion_window: int,
    entry_z: float,
    exit_z: float,
    strategy_parameters: Mapping[str, int | float | str] | None = None,
) -> ResearchStrategy:
    """Construct a supported deterministic strategy from CLI-friendly values."""

    parameters: dict[str, int | float | str] = {}

    if strategy_name == "moving_average_crossover":
        parameters.update(
            {
                "fast_window": fast_window,
                "slow_window": slow_window,
            }
        )
    elif strategy_name == "zscore_mean_reversion":
        parameters.update(
            {
                "window": mean_reversion_window,
                "entry_z": entry_z,
                "exit_z": exit_z,
            }
        )

    parameters.update(strategy_parameters or {})

    return build_strategy(strategy_name, parameters)


def _parameter_variants(
    *,
    strategy_name: StrategyName,
    fast_window: int,
    slow_window: int,
    mean_reversion_window: int,
    entry_z: float,
    exit_z: float,
    strategy_parameters: Mapping[str, int | float | str] | None = None,
) -> tuple[ResearchStrategy, ...]:
    """Build a declared neighborhood instead of optimizing on observed returns."""

    strategy = _build_strategy(
        strategy_name=strategy_name,
        fast_window=fast_window,
        slow_window=slow_window,
        mean_reversion_window=mean_reversion_window,
        entry_z=entry_z,
        exit_z=exit_z,
        strategy_parameters=strategy_parameters,
    )

    return neighboring_variants(
        strategy_name,
        strategy.descriptor.parameters,
    )
