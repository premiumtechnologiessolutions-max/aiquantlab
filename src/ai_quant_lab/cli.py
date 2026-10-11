from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, NoReturn, cast, get_args

import typer

from ai_quant_lab.agents.conversation import AgentConversationService
from ai_quant_lab.backtesting import BacktestConfig
from ai_quant_lab.broker import MT5DemoGateway
from ai_quant_lab.campaigns import run_research_campaign
from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.backfill import HistoricalBackfillResult, backfill_market_data
from ai_quant_lab.data.csv_source import CsvMarketDataSource
from ai_quant_lab.data.ingestion import (
    IngestionResult,
    ingest_market_data,
)
from ai_quant_lab.data.mt5_source import MetaTrader5MarketDataSource
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.data.update import (
    DatasetUpdateResult,
    update_market_data,
)
from ai_quant_lab.monitoring import DemoMarketMonitor, MonitorConfig
from ai_quant_lab.research import run_research_experiment
from ai_quant_lab.runtime import LabRuntime, LabRuntimeConfig
from ai_quant_lab.strategies import (
    STRATEGY_CATALOG,
    SUPPORTED_STRATEGIES,
    StrategyName,
    normalize_strategy_name,
)
from ai_quant_lab.web import serve_voice_dashboard

app = typer.Typer(
    name="ai-quant-lab",
    help="AI Quant Lab research and market-data command line interface.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run the AI Quant Lab command group."""


@app.command("ingest-csv")
def ingest_csv(
    csv_path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to the historical market CSV file.",
        ),
    ],
    pair: Annotated[
        str,
        typer.Option(
            "--pair",
            help="Forex pair such as EURUSD.",
        ),
    ],
    timeframe: Annotated[
        str,
        typer.Option(
            "--timeframe",
            help="Timeframe: M1, M5, M15, H1, H4, or D1.",
        ),
    ],
    start: Annotated[
        str,
        typer.Option(
            "--start",
            help="Timezone-aware ISO start time.",
        ),
    ],
    end: Annotated[
        str,
        typer.Option(
            "--end",
            help="Timezone-aware ISO end time.",
        ),
    ],
    output_root: Annotated[
        Path,
        typer.Option(
            "--output-root",
            help="Root directory for processed datasets.",
        ),
    ] = Path("data/processed"),
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Allow replacement of an existing dataset.",
        ),
    ] = False,
) -> None:
    """Ingest one historical CSV dataset into canonical storage."""

    validated_pair = _parse_pair(pair)
    validated_timeframe = _parse_timeframe(timeframe)
    start_time = _parse_datetime(
        start,
        name="start",
    )
    end_time = _parse_datetime(
        end,
        name="end",
    )

    source = CsvMarketDataSource(
        csv_path,
        source_name="csv-cli",
    )

    store = ParquetMarketStore(output_root)

    try:
        result = ingest_market_data(
            source=source,
            store=store,
            pair=validated_pair,
            timeframe=validated_timeframe,
            start=start_time,
            end=end_time,
            overwrite=overwrite,
        )
    except (
        ValueError,
        FileExistsError,
    ) as error:
        _fail_operation(
            operation="Ingestion",
            error=error,
        )

    _print_ingestion_result(result)


@app.command("ingest-mt5")
def ingest_mt5(
    pair: Annotated[
        str,
        typer.Option(
            "--pair",
            help="Forex pair such as EURUSD.",
        ),
    ],
    timeframe: Annotated[
        str,
        typer.Option(
            "--timeframe",
            help="Timeframe: M1, M5, M15, H1, H4, or D1.",
        ),
    ],
    start: Annotated[
        str,
        typer.Option(
            "--start",
            help="Timezone-aware ISO start time.",
        ),
    ],
    end: Annotated[
        str,
        typer.Option(
            "--end",
            help="Timezone-aware ISO end time.",
        ),
    ],
    terminal_path: Annotated[
        Path | None,
        typer.Option(
            "--terminal-path",
            exists=True,
            dir_okay=False,
            readable=True,
            help=(
                "Optional path to terminal64.exe. "
                "If omitted, MetaTrader 5 auto-discovery is used."
            ),
        ),
    ] = None,
    broker_symbol: Annotated[
        str | None,
        typer.Option(
            "--broker-symbol",
            help=(
                "Optional broker-specific symbol, "
                "such as EURUSD.a or EURUSDm."
            ),
        ),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option(
            "--output-root",
            help="Root directory for processed datasets.",
        ),
    ] = Path("data/processed"),
    timeout_ms: Annotated[
        int,
        typer.Option(
            "--timeout-ms",
            min=1,
            help="Maximum MetaTrader 5 connection time in milliseconds.",
        ),
    ] = 60_000,
    portable: Annotated[
        bool,
        typer.Option(
            "--portable",
            help="Initialize MetaTrader 5 in portable mode.",
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Allow replacement of an existing dataset.",
        ),
    ] = False,
) -> None:
    """Ingest historical bars from a local MetaTrader 5 terminal."""

    validated_pair = _parse_pair(pair)
    validated_timeframe = _parse_timeframe(timeframe)
    start_time = _parse_datetime(
        start,
        name="start",
    )
    end_time = _parse_datetime(
        end,
        name="end",
    )

    source = _build_mt5_source(
        pair=validated_pair,
        terminal_path=terminal_path,
        broker_symbol=broker_symbol,
        timeout_ms=timeout_ms,
        portable=portable,
    )

    store = ParquetMarketStore(output_root)

    try:
        result = ingest_market_data(
            source=source,
            store=store,
            pair=validated_pair,
            timeframe=validated_timeframe,
            start=start_time,
            end=end_time,
            overwrite=overwrite,
        )
    except (
        ValueError,
        FileExistsError,
        RuntimeError,
    ) as error:
        _fail_operation(
            operation="Ingestion",
            error=error,
        )

    _print_ingestion_result(result)


@app.command("update-mt5")
def update_mt5(
    pair: Annotated[
        str,
        typer.Option(
            "--pair",
            help="Forex pair such as EURUSD.",
        ),
    ],
    timeframe: Annotated[
        str,
        typer.Option(
            "--timeframe",
            help="Timeframe: M1, M5, M15, H1, H4, or D1.",
        ),
    ],
    start: Annotated[
        str,
        typer.Option(
            "--start",
            help="Timezone-aware ISO start time.",
        ),
    ],
    end: Annotated[
        str,
        typer.Option(
            "--end",
            help="Timezone-aware ISO end time.",
        ),
    ],
    terminal_path: Annotated[
        Path | None,
        typer.Option(
            "--terminal-path",
            exists=True,
            dir_okay=False,
            readable=True,
            help=(
                "Optional path to terminal64.exe. "
                "If omitted, MetaTrader 5 auto-discovery is used."
            ),
        ),
    ] = None,
    broker_symbol: Annotated[
        str | None,
        typer.Option(
            "--broker-symbol",
            help=(
                "Optional broker-specific symbol, "
                "such as EURUSD.a or EURUSDm."
            ),
        ),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option(
            "--output-root",
            help="Root directory containing processed datasets.",
        ),
    ] = Path("data/processed"),
    timeout_ms: Annotated[
        int,
        typer.Option(
            "--timeout-ms",
            min=1,
            help="Maximum MetaTrader 5 connection time in milliseconds.",
        ),
    ] = 60_000,
    portable: Annotated[
        bool,
        typer.Option(
            "--portable",
            help="Initialize MetaTrader 5 in portable mode.",
        ),
    ] = False,
) -> None:
    """Fetch and safely merge an MT5 batch into a stored dataset."""

    validated_pair = _parse_pair(pair)
    validated_timeframe = _parse_timeframe(timeframe)
    start_time = _parse_datetime(
        start,
        name="start",
    )
    end_time = _parse_datetime(
        end,
        name="end",
    )

    source = _build_mt5_source(
        pair=validated_pair,
        terminal_path=terminal_path,
        broker_symbol=broker_symbol,
        timeout_ms=timeout_ms,
        portable=portable,
    )

    store = ParquetMarketStore(output_root)

    try:
        result = update_market_data(
            source=source,
            store=store,
            pair=validated_pair,
            timeframe=validated_timeframe,
            start=start_time,
            end=end_time,
        )
    except (
        ValueError,
        RuntimeError,
    ) as error:
        _fail_operation(
            operation="Update",
            error=error,
        )

    _print_update_result(result)


@app.command("backfill-mt5")
def backfill_mt5(
    pair: Annotated[str, typer.Option("--pair", help="Forex pair such as EURUSD.")],
    timeframe: Annotated[
        str,
        typer.Option("--timeframe", help="Timeframe: M1, M5, M15, H1, H4, or D1."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="Timezone-aware ISO start time."),
    ],
    end: Annotated[
        str,
        typer.Option("--end", help="Timezone-aware ISO end time."),
    ],
    chunk_days: Annotated[
        int,
        typer.Option("--chunk-days", min=1, help="Days fetched per safe MT5 chunk."),
    ] = 30,
    terminal_path: Annotated[
        Path | None,
        typer.Option(
            "--terminal-path",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    broker_symbol: Annotated[
        str | None,
        typer.Option("--broker-symbol"),
    ] = None,
    output_root: Annotated[
        Path,
        typer.Option("--output-root"),
    ] = Path("data/processed"),
    timeout_ms: Annotated[
        int,
        typer.Option("--timeout-ms", min=1),
    ] = 60_000,
    portable: Annotated[
        bool,
        typer.Option("--portable"),
    ] = False,
) -> None:
    """Backfill a long MT5 history in resumable, conflict-checked chunks."""

    validated_pair = _parse_pair(pair)
    validated_timeframe = _parse_timeframe(timeframe)
    source = _build_mt5_source(
        pair=validated_pair,
        terminal_path=terminal_path,
        broker_symbol=broker_symbol,
        timeout_ms=timeout_ms,
        portable=portable,
    )

    try:
        result = backfill_market_data(
            source=source,
            store=ParquetMarketStore(output_root),
            pair=validated_pair,
            timeframe=validated_timeframe,
            start=_parse_datetime(start, name="start"),
            end=_parse_datetime(end, name="end"),
            chunk_days=chunk_days,
        )
    except (ValueError, RuntimeError) as error:
        _fail_operation(operation="Backfill", error=error)

    _print_backfill_result(result)


@app.command("research-run")
def research_run(
    pair: Annotated[
        str,
        typer.Option("--pair", help="Forex pair such as EURUSD."),
    ],
    timeframe: Annotated[
        str,
        typer.Option("--timeframe", help="Timeframe: M1, M5, M15, H1, H4, or D1."),
    ],
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            help=(
                "moving_average_crossover, zscore_mean_reversion, "
                "or buy_and_hold."
            ),
        ),
    ] = "moving_average_crossover",
    data_root: Annotated[
        Path,
        typer.Option("--data-root", help="Root containing canonical Parquet datasets."),
    ] = Path("data/processed"),
    output_root: Annotated[
        Path,
        typer.Option("--output-root", help="Root for experiment reports."),
    ] = Path("data/experiments"),
    fast_window: Annotated[
        int,
        typer.Option("--fast-window", min=2),
    ] = 20,
    slow_window: Annotated[
        int,
        typer.Option("--slow-window", min=3),
    ] = 50,
    mean_reversion_window: Annotated[
        int,
        typer.Option("--mean-reversion-window", min=3),
    ] = 30,
    entry_z: Annotated[
        float,
        typer.Option("--entry-z", min=0.01),
    ] = 1.5,
    exit_z: Annotated[
        float,
        typer.Option("--exit-z", min=0.0),
    ] = 0.25,
    quantity: Annotated[
        float,
        typer.Option("--quantity", min=1.0, help="Simulated position units."),
    ] = 10_000.0,
    slippage_points: Annotated[
        float,
        typer.Option("--slippage-points", min=0.0),
    ] = 1.0,
) -> None:
    """Run the complete safe research/backtest/validation/report pipeline."""

    validated_pair = _parse_pair(pair)
    validated_timeframe = _parse_timeframe(timeframe)
    validated_strategy = _parse_strategy(strategy)

    try:
        result = run_research_experiment(
            pair=validated_pair,
            timeframe=validated_timeframe,
            data_root=data_root,
            output_root=output_root,
            strategy_name=validated_strategy,
            fast_window=fast_window,
            slow_window=slow_window,
            mean_reversion_window=mean_reversion_window,
            entry_z=entry_z,
            exit_z=exit_z,
            backtest_config=BacktestConfig(
                quantity=quantity,
                slippage_points=slippage_points,
            ),
        )
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        _fail_operation(
            operation="Research run",
            error=error,
        )

    typer.echo("Research run complete")
    typer.echo(f"Experiment: {result.experiment_id}")
    typer.echo(f"Net profit: {result.backtest.metrics.net_profit:.2f}")
    typer.echo(f"Trades: {result.backtest.metrics.trade_count}")
    typer.echo(
        "Quantitative gates passed: "
        f"{result.validation.passed_quantitative_gates}"
    )
    typer.echo("Live trading approved: False")
    typer.echo(f"JSON report: {result.json_report_path}")
    typer.echo(f"Markdown report: {result.markdown_report_path}")
    typer.echo(f"Intelligence profile: {result.intelligence_profile_path}")


@app.command("agent-status")
def agent_status(
    command: Annotated[
        str,
        typer.Argument(help="Agent name or team command, such as 'حالة الفريق'."),
    ] = "حالة الفريق",
    database: Annotated[
        Path,
        typer.Option(
            "--database",
            help="Operational SQLite database containing real runtime state.",
        ),
    ] = Path("data/operational/lab.sqlite3"),
) -> None:
    """Ask an agent using its persisted task, message, and journal state."""

    runtime = LabRuntime(
        LabRuntimeConfig(operational_database=database),
    )
    result = AgentConversationService(runtime).ask(command)
    typer.echo(result.reply)

    if not result.success:
        raise typer.Exit(code=1)


@app.command("runtime-once")
def runtime_once(
    database: Annotated[
        Path,
        typer.Option(
            "--database",
            help="Operational SQLite database used to recover tasks and messages.",
        ),
    ] = Path("data/operational/lab.sqlite3"),
) -> None:
    """Start the persistent runtime, run one scheduler tick, and stop safely."""

    runtime = LabRuntime(
        LabRuntimeConfig(operational_database=database),
    )
    runtime.start()
    jobs = runtime.run_once()
    tasks = runtime.task_board.all_tasks()
    runtime.stop()

    typer.echo("Runtime tick complete")
    typer.echo(f"Tasks preserved: {len(tasks)}")
    typer.echo(f"Jobs run: {len(jobs)}")
    typer.echo(f"Database: {database}")


@app.command("strategy-list")
def strategy_list() -> None:
    """List every deterministic strategy available to research and monitoring."""

    typer.echo(f"Available strategies: {len(STRATEGY_CATALOG)}")

    for specification in STRATEGY_CATALOG:
        typer.echo(
            f"- {specification.name} [{specification.family.value}]: "
            f"{specification.description}"
        )


@app.command("research-campaign")
def research_campaign(
    pair: Annotated[str, typer.Option("--pair")] = "EURUSD",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "M15",
    strategies: Annotated[
        str,
        typer.Option(
            "--strategies",
            help="Comma-separated names, or 'all' for the complete catalog.",
        ),
    ] = "all",
    data_root: Annotated[Path, typer.Option("--data-root")] = Path("data/processed"),
    experiment_root: Annotated[
        Path,
        typer.Option("--experiment-root"),
    ] = Path("data/experiments"),
    campaign_root: Annotated[
        Path,
        typer.Option("--campaign-root"),
    ] = Path("data/campaigns"),
) -> None:
    """Compare multiple strategies on one identical canonical dataset."""

    requested = (
        SUPPORTED_STRATEGIES
        if strategies.strip().casefold() == "all"
        else tuple(
            _parse_strategy(part)
            for part in strategies.split(",")
            if part.strip()
        )
    )

    try:
        result = run_research_campaign(
            pair=_parse_pair(pair),
            timeframe=_parse_timeframe(timeframe),
            strategy_names=requested,
            data_root=data_root,
            experiment_root=experiment_root,
            campaign_root=campaign_root,
        )
    except (FileNotFoundError, RuntimeError, TypeError, ValueError) as error:
        _fail_operation(operation="Research campaign", error=error)

    typer.echo("Research campaign complete")
    typer.echo(f"Campaign: {result.campaign_id}")
    typer.echo(f"Strategies compared: {len(result.entries)}")
    typer.echo(f"Research leader: {result.research_leader}")
    typer.echo("Live trading approved: False")
    typer.echo(f"Report: {result.markdown_path}")


@app.command("mt5-demo-status")
def mt5_demo_status() -> None:
    """Verify that the configured local MT5 terminal is using a demo account."""

    gateway = MT5DemoGateway()

    try:
        account = gateway.connect()
    except (RuntimeError, ValueError) as error:
        _fail_operation(operation="MT5 demo connection", error=error)

    typer.echo("Verified MT5 demo account")
    typer.echo(f"Server: {account.server}")
    typer.echo(f"Login: ****{account.login_last_four}")
    typer.echo(f"Balance: {account.balance:.2f} {account.currency}")
    typer.echo(f"Equity: {account.equity:.2f}")
    typer.echo(f"Trade allowed: {account.trade_allowed}")
    gateway.disconnect()


@app.command("mt5-demo-scan")
def mt5_demo_scan(
    pairs: Annotated[
        str,
        typer.Option("--pairs", help="Comma-separated supported forex pairs."),
    ] = "EURUSD",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "M15",
    lookback_bars: Annotated[
        int,
        typer.Option("--lookback-bars", min=60, max=10_000),
    ] = 300,
) -> None:
    """Run one live-data ensemble scan without sending a broker order."""

    gateway = MT5DemoGateway()
    monitor = DemoMarketMonitor(
        gateway,
        MonitorConfig(
            pairs=_parse_pairs(pairs),
            timeframe=_parse_timeframe(timeframe),
            lookback_bars=lookback_bars,
        ),
    )

    try:
        scans = monitor.scan_once()
    except (RuntimeError, TypeError, ValueError) as error:
        _fail_operation(operation="MT5 demo scan", error=error)
    finally:
        gateway.disconnect()

    for scan in scans:
        typer.echo(
            f"{scan.pair} {scan.timeframe}: regime={scan.regime.value}, "
            f"consensus={scan.consensus.name.lower()}, "
            f"long_votes={scan.long_votes}, short_votes={scan.short_votes}"
        )


@app.command("voice-dashboard")
def voice_dashboard(
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65_535),
    ] = 8765,
    pairs: Annotated[
        str,
        typer.Option("--pairs", help="Pairs monitored while the dashboard is running."),
    ] = "EURUSD",
    timeframe: Annotated[str, typer.Option("--timeframe")] = "M15",
    monitor_interval: Annotated[
        float,
        typer.Option("--monitor-interval", min=5, max=3_600),
    ] = 30.0,
    auto_monitor: Annotated[
        bool,
        typer.Option("--auto-monitor/--no-auto-monitor"),
    ] = True,
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser/--no-open-browser"),
    ] = True,
) -> None:
    """Open the localhost voice UI and continuously run the safe agent runtime."""

    serve_voice_dashboard(
        port=port,
        open_browser=open_browser,
        auto_monitor=auto_monitor,
        monitor_interval_seconds=monitor_interval,
        monitor_config=MonitorConfig(
            pairs=_parse_pairs(pairs),
            timeframe=_parse_timeframe(timeframe),
        ),
    )


def _build_mt5_source(
    *,
    pair: ForexPair,
    terminal_path: Path | None,
    broker_symbol: str | None,
    timeout_ms: int,
    portable: bool,
) -> MetaTrader5MarketDataSource:
    """Create a configured read-only MetaTrader 5 source."""

    symbol_map: dict[ForexPair, str] | None = None

    if broker_symbol is not None:
        normalized_symbol = broker_symbol.strip()

        if not normalized_symbol:
            raise typer.BadParameter(
                "The broker symbol cannot be empty.",
            )

        symbol_map = {
            pair: normalized_symbol,
        }

    return MetaTrader5MarketDataSource(
        terminal_path=terminal_path,
        timeout_ms=timeout_ms,
        portable=portable,
        symbol_map=symbol_map,
    )


def _parse_pair(
    value: str,
) -> ForexPair:
    """Validate and normalize a supported forex pair."""

    normalized = value.strip().upper()

    if normalized not in get_args(ForexPair):
        supported = ", ".join(
            get_args(ForexPair),
        )

        raise typer.BadParameter(
            f"Unsupported pair '{value}'. "
            f"Supported pairs: {supported}.",
        )

    return cast(
        ForexPair,
        normalized,
    )


def _parse_timeframe(
    value: str,
) -> Timeframe:
    """Validate and normalize a supported timeframe."""

    normalized = value.strip().upper()

    if normalized not in get_args(Timeframe):
        supported = ", ".join(
            get_args(Timeframe),
        )

        raise typer.BadParameter(
            f"Unsupported timeframe '{value}'. "
            f"Supported timeframes: {supported}.",
        )

    return cast(
        Timeframe,
        normalized,
    )


def _parse_strategy(
    value: str,
) -> StrategyName:
    """Validate and normalize one supported research strategy name."""

    try:
        return normalize_strategy_name(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


def _parse_pairs(value: str) -> tuple[ForexPair, ...]:
    """Parse a non-empty unique comma-separated pair list."""

    pairs = tuple(_parse_pair(part) for part in value.split(",") if part.strip())

    if not pairs:
        raise typer.BadParameter("At least one forex pair is required.")

    if len(pairs) != len(set(pairs)):
        raise typer.BadParameter("Forex pairs must be unique.")

    return pairs


def _parse_datetime(
    value: str,
    *,
    name: str,
) -> datetime:
    """Parse a timezone-aware ISO datetime."""

    normalized = value.strip().replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            normalized,
        )
    except ValueError as error:
        raise typer.BadParameter(
            f"Invalid {name} datetime: {value}",
        ) from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise typer.BadParameter(
            f"The {name} datetime must include timezone information.",
        )

    return parsed


def _fail_operation(
    *,
    operation: str,
    error: Exception,
) -> NoReturn:
    """Print a controlled operation error and stop the command."""

    typer.echo(
        f"{operation} failed: {error}",
        err=True,
    )

    raise typer.Exit(
        code=1,
    ) from error


def _print_ingestion_result(
    result: IngestionResult,
) -> None:
    """Print one successful ingestion result."""

    typer.echo("Ingestion complete")
    typer.echo(f"Source: {result.source}")
    typer.echo(f"Pair: {result.pair}")
    typer.echo(f"Timeframe: {result.timeframe}")
    typer.echo(f"Bars written: {result.bars_written}")
    typer.echo(f"Missing intervals: {result.missing_intervals}")
    typer.echo(f"Dataset: {result.dataset_path}")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo(f"SHA-256: {result.dataset_sha256}")


def _print_update_result(
    result: DatasetUpdateResult,
) -> None:
    """Print one successful dataset update result."""

    typer.echo("Dataset update complete")
    typer.echo(f"Source: {result.source}")
    typer.echo(f"Pair: {result.pair}")
    typer.echo(f"Timeframe: {result.timeframe}")
    typer.echo(f"Existing bars: {result.existing_bars}")
    typer.echo(f"Fetched bars: {result.fetched_bars}")
    typer.echo(f"Overlapping bars: {result.overlapping_bars}")
    typer.echo(f"New bars: {result.new_bars}")
    typer.echo(f"Total bars: {result.total_bars}")
    typer.echo(f"Dataset: {result.dataset_path}")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo(f"SHA-256: {result.dataset_sha256}")


def _print_backfill_result(
    result: HistoricalBackfillResult,
) -> None:
    """Print one completed resumable historical backfill."""

    typer.echo("Historical backfill complete")
    typer.echo(f"Source: {result.source}")
    typer.echo(f"Pair: {result.pair}")
    typer.echo(f"Timeframe: {result.timeframe}")
    typer.echo(f"Chunks: {result.chunks_total}")
    typer.echo(f"Fetched bars: {result.fetched_bars}")
    typer.echo(f"New bars: {result.new_bars}")
    typer.echo(f"Final bars: {result.final_bars}")
    typer.echo(f"Dataset: {result.dataset_path}")
    typer.echo(f"Manifest: {result.manifest_path}")
    typer.echo(f"SHA-256: {result.dataset_sha256}")
