# AI Quant Lab

AI Quant Lab is a safe, auditable institutional-style quantitative-research laboratory
for the seven major forex pairs on M1, M5, M15, H1, H4, and D1. It combines deterministic
Python research, a persistent named-agent runtime, a localhost voice dashboard, and a
verified MetaTrader 5 demo-account monitor.

It blocks real and contest MT5 accounts. Optional broker orders require a verified
demo account, a disabled-by-default switch, strict limits, and an explicit human
confirmation phrase. It does **not** promise profits or authorize live trading.

## What is implemented

- Validated CSV and MetaTrader 5 ingestion plus completed-bar demo monitoring.
- Conflict-safe updates and resumable historical backfills.
- Canonical Parquet datasets, manifests, data-quality checks, and SHA-256 identity.
- Persistent Atlas/Vega/Nova/Chronos/Iris/Sentinel/Aegis/Oracle/Echo/Forge team.
- Shared task board, delegation, inbox/outbox, activity journal, and real status replies.
- SQLite recovery, scheduler, heartbeats, idempotent daily work, and daily reports.
- Cost-aware next-bar backtesting with spread, slippage, commission, and no look-ahead fills.
- Sixteen causal executable strategies plus 35 truthful institutional blueprints whose
  missing multi-asset or external-feed requirements are shown instead of fabricated.
- Pair/timeframe-calibrated three-state Gaussian HMM using Baum-Welch EM, blended with a
  two-component GMM, Bayesian change-point evidence, a local-linear Kalman filter,
  autocorrelation, and spread stress.
- Purged walk-forward, Monte Carlo, parameter-stability, and blind OOS validation tools.
- Immutable strategy versions, append-only experiments, and pair intelligence profiles.
- Research-only strategy ranking plus append-only shadow/paper simulation ledger.
- Multi-strategy research campaigns with comparable JSON/Markdown rankings.
- Local Arabic voice/text dashboard with continuous listening after one activation,
  sticky follow-up context, agent wake names, and a distinct speech profile for every agent.
- Verified MT5 demo connection, sanitized account/position views, and guarded manual
  demo orders. Non-demo accounts are rejected before market access or execution.
- Optional Anthropic Messages API provider with environment-only credentials and hard budgets.
- JSON and Markdown experiment reports with the complete agent audit trail.
- A restart-safe continuous research loop: Vega → Iris → Oracle → Nova → Chronos →
  Sentinel → Aegis → Forge → Echo, coordinated by Atlas on each new completed bar.
- Replayable Thompson-sampling strategy selection for every pair/timeframe/regime, with
  persistent Beta posteriors updated only from the final deterministic Quant Score.
- Deterministic genetic crossover/mutation in Forge; offspring remain untested proposals
  until a later campaign sends them through Chronos, Sentinel, and Aegis.
- Optional bounded LLM assistance for Nova/Sentinel/Echo that can propose or explain but
  cannot calculate official numbers, alter gates, approve trading, or reach `order_send`.
- A central SQLite registry for exact dataset versions, regimes, hypotheses, every failed or
  successful trial, Quant Scores, risk decisions, and champion–challenger candidates.
- A Quant Command Center with a persistent kill switch, live stage progress, agent tools,
  inputs, outputs, errors, messages, and one recorded hand-off between every stage.

See [Institutional Research V4](docs/INSTITUTIONAL_RESEARCH_V4.md) and
[Project Status](docs/PROJECT_STATUS.md) for the exact boundary of this version.

## Windows installation

Use Python 3.12 and PowerShell from the project folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

MetaTrader 5 integration is installed only on Windows. CSV research and the rest
of the project can run without MT5.

Verify the installation:

```powershell
ruff check src tests scripts
mypy src
pytest
```

## Fastest start: voice dashboard + MT5 Demo

1. Extract the ZIP, open the inner `AI_QUANT_LAB` folder, then open MetaTrader 5 and
   log in to a **Demo** account.
2. Double-click `START_AI_QUANT_LAB.bat`. On first start it creates a dedicated
   `.venv312` and installs the project automatically. No activation command is required.

The equivalent PowerShell command is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_voice_dashboard.ps1
```

3. Chrome or Edge opens `http://127.0.0.1:8765`. Allow microphone permission.
4. Press 🎙 once to arm continuous listening, then call an agent by name:

```text
يا Atlas شو وضع الفريق؟
يا Iris شو حالة السوق؟
يا Aegis شو وضع الحساب والصفقات؟
يا Nova خبرني عن الاستراتيجيات والتجارب
```

Speech recognition and speech synthesis run through browser capabilities. Typed chat
always remains available. The dashboard binds to localhost only, requires a random
session token for every mutation, and the browser never receives or displays the MT5 password.
Each agent receives a separate installed Arabic voice when several are available;
otherwise rate and pitch profiles keep their spoken identities distinct.

Manual environment setup is also supported:

```powershell
$env:AI_QUANT_MT5_TERMINAL_PATH = "C:\Program Files\MetaTrader 5\terminal64.exe"
$env:AI_QUANT_MT5_LOGIN = "YOUR_DEMO_LOGIN"
$env:AI_QUANT_MT5_SERVER = "YOUR_BROKER_DEMO_SERVER"
$env:AI_QUANT_MT5_PASSWORD = "YOUR_DEMO_PASSWORD"
ai-quant-lab voice-dashboard --pairs EURUSD,GBPUSD --timeframe M15
```

Credentials remain process environment values and are not written to reports, TOML,
SQLite, browser storage, or source files. Clear the environment when finished.

## Get market data

Import a CSV:

```powershell
ai-quant-lab ingest-csv .\data\raw\eurusd.csv `
  --pair EURUSD --timeframe M15 `
  --start 2026-01-01T00:00:00+00:00 `
  --end 2026-08-01T00:00:00+00:00
```

Import or update from a local MT5 terminal:

```powershell
ai-quant-lab ingest-mt5 --pair EURUSD --timeframe M15 `
  --start 2026-01-01T00:00:00+00:00 `
  --end 2026-08-01T00:00:00+00:00

ai-quant-lab update-mt5 --pair EURUSD --timeframe M15 `
  --start 2026-07-01T00:00:00+00:00 `
  --end 2026-08-01T00:00:00+00:00

ai-quant-lab backfill-mt5 --pair EURUSD --timeframe M15 `
  --start 2020-01-01T00:00:00+00:00 `
  --end 2026-08-01T00:00:00+00:00 --chunk-days 30
```

Broker suffixes such as `EURUSD.a` can be passed with `--broker-symbol`.

## Run research experiments and strategy campaigns

```powershell
ai-quant-lab research-run --pair EURUSD --timeframe M15 `
  --strategy moving_average_crossover `
  --fast-window 20 --slow-window 50
```

Supported deterministic strategies:

- `moving_average_crossover`
- `ema_crossover`
- `macd_momentum`
- `roc_momentum`
- `donchian_breakout`
- `zscore_mean_reversion`
- `rsi_mean_reversion`
- `bollinger_reversion`
- `kalman_adaptive_trend` — latent level/slope state-space filter
- `multi_horizon_vol_trend` — volatility-scaled multi-horizon trend
- `variance_ratio_regime_switch` — statistical persistence/reversion switch
- `garman_klass_vol_breakout` — prior-OHLC range-volatility breakout
- `time_series_momentum` — volatility-normalized multi-horizon time-series momentum
- `kalman_mean_reversion` — latent fair-value residual reversion
- `volatility_breakout` — causal compression/expansion breakout with spread awareness
- `buy_and_hold`

List the live catalog:

```powershell
ai-quant-lab strategy-list
```

Compare every strategy on the exact same dataset:

```powershell
ai-quant-lab research-campaign --pair EURUSD --timeframe M15 --strategies all
```

The campaign writes a ranked JSON and Markdown summary under `data/campaigns`.
The first row is called a **research leader**, never a live-trading approval.

## Continuous institutional research

The continuous program uses two separate layers. The deterministic execution layer owns
all official metrics, validation, sizing, and gates. The bounded Brain layer may expand the
search space through replayable Thompson selection, pair-specific HMM calibration, genetic
parameter proposals, and optional qualitative LLM output. No Brain result bypasses the
existing evidence chain.

With the dashboard open and MT5 Demo connected, every newly completed configured bar can
start one idempotent campaign. The chain freezes the exact input bars, records unavailable
feeds, declares a falsifiable hypothesis before seeing the holdout, runs an embargoed 60/40
split and purged walk-forward validation, stresses costs and neighboring parameters, applies
multiple-testing/PBO evidence, and lets Aegis decide only whether a candidate may enter
**shadow research**. Paper, Champion, and live promotion remain false and require a later
human-controlled process.

The Quant Command Center has explicit Start, Pause, Emergency Stop, and Reset controls.
Click any Agent card to inspect its real task history, tools, inputs, outputs, failures, and
inter-agent hand-offs. The registry and controls survive a restart.

OHLCV, tick volume, and MT5 spread are used when present. Order book, trade flow, funding,
open interest, liquidations, options volatility, macro, cross-asset, and news inputs are
capabilities—not invented data. Their blueprints remain unavailable until a real licensed
provider and aligned history are connected.

Every run creates:

- `data/experiments/<experiment-id>/report.json`
- `data/experiments/<experiment-id>/report.md`
- `data/experiments/registry.sqlite3`
- `data/intelligence/<pair>/<timeframe>/<profile-id>.json`

A positive backtest is not a promotion. The report records uncompleted gates as
`not_run`, and live eligibility is always false.

## Run and talk to the agent team

Voice dashboard:

```powershell
ai-quant-lab voice-dashboard --pairs EURUSD --timeframe M15
```

One safe scheduler tick:

```powershell
ai-quant-lab runtime-once
```

Persistent foreground runtime:

```powershell
ai-quant-lab-runtime
```

Persistent text conversation:

```powershell
python -X utf8 scripts\chat_with_agents.py
```

Examples:

```text
يا Atlas شو وضع الفريق؟
يا Vega شو مهامك؟
شو عمل الفريق اليوم؟
```

Replies are built from the real task board, SQLite messages, and activity journal.
When no paid model is enabled, the deterministic runtime remains fully usable.
Account, market, position, strategy, and campaign questions are answered from real
local state before any optional model provider is considered.

## MT5 demo monitor and optional manual orders

Verify the connected account and run a single ensemble scan:

```powershell
ai-quant-lab mt5-demo-status
ai-quant-lab mt5-demo-scan --pairs EURUSD,GBPUSD --timeframe M15
```

Continuous dashboard scans create append-only shadow decisions by default. They do
not send broker orders automatically.

The advanced dashboard order form remains locked unless you deliberately set:

```powershell
$env:AI_QUANT_ENABLE_DEMO_ORDERS = "true"
$env:AI_QUANT_DEMO_MAX_VOLUME = "0.10"
```

Each order still requires:

- a verified MT5 **Demo** account;
- a fresh quote and acceptable spread;
- broker-compatible lot minimum, maximum, and step;
- mandatory stop-loss and take-profit distances;
- the exact confirmation phrase `DEMO ONLY`;
- successful MT5 `order_check` before `order_send`.

Real and contest accounts are structurally refused even if demo orders are enabled.

## Optional Anthropic provider and cost controls

Paid calls are disabled in `configs/agents.toml`. To opt in deliberately:

1. Set `[providers.anthropic].enabled = true`.
2. Enter an exact current model name and its current input/output prices.
3. Change only the chosen agents from `provider = "disabled"` to `"anthropic"`.
4. Keep low `maximum_cost_per_request_usd` and `maximum_total_cost_usd` values.
5. Set the key in PowerShell—never in TOML, source code, prompts, logs, or chat:

```powershell
$env:ANTHROPIC_API_KEY = "your-new-key"
```

The adapter makes at most one request per user turn, performs no automatic paid
retry, estimates worst-case cost before sending, and records returned token usage.
If rates are left at zero, it refuses to call the API.

## Safety boundary

The normal deterministic path is:

```text
Data → Strategy Signal → Backtest/Validation → Risk Policy → Shadow/Paper Ledger
```

The optional broker path is separate:

```text
Human action → Demo-account proof → Quote/risk checks → order_check → MT5 Demo only
```

There is no real-money mode and no automatic route from a strategy signal to
`order_send`. Paper promotion still requires explicit human approval in the registry.
Statistical evidence requires adequate real history plus time-based shadow and paper
trials; passing automated tests does not prove profitability.

More detail is in [Architecture](docs/ARCHITECTURE.md) and
[Operations](docs/OPERATIONS.md). The exact MT5/voice steps are in
[Voice and MT5 Demo](docs/VOICE_AND_MT5_DEMO.md).
