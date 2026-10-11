# Windows Operations

## Recommended terminal

Use Windows Terminal or the VS Code terminal with UTF-8:

```powershell
chcp 65001
python -X utf8 scripts\chat_with_agents.py
```

A font with Arabic glyph support improves rendering. Terminal display direction is
separate from agent-name routing and stored UTF-8 content.

## Voice dashboard

The simplest secure start is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_voice_dashboard.ps1
```

The script asks for Demo credentials only in the current PowerShell process, starts
the localhost dashboard, and clears credential environment variables on exit. The
advanced demo-order switch stays disabled.

Manual start:

```powershell
ai-quant-lab voice-dashboard --pairs EURUSD,GBPUSD --timeframe M15
```

Use Chrome or Edge, allow microphone access for `127.0.0.1`, and keep the terminal
window open. `Ctrl+C` stops the scheduler, disconnects MT5, and records a controlled
runtime stop.

See [Voice and MT5 Demo](VOICE_AND_MT5_DEMO.md) for connection and troubleshooting.

## Always-on startup

After verifying `runtime-once`, create a Windows Task Scheduler entry that runs at
sign-in from the project directory:

```text
Program: C:\path\to\AI_QUANT_LAB\.venv\Scripts\python.exe
Arguments: -X utf8 scripts\run_lab_runtime.py
Start in: C:\path\to\AI_QUANT_LAB
```

Configure Task Scheduler to restart the task after failure. `LabRuntime` restores
SQLite state, writes heartbeats, prevents duplicate daily tasks, and preserves
unfinished work on controlled shutdown.

## Recovery checks

```powershell
ai-quant-lab runtime-once
ai-quant-lab agent-status "يا Atlas شو وضع الفريق؟"
pytest
ai-quant-lab mt5-demo-status
ai-quant-lab mt5-demo-scan --pairs EURUSD --timeframe M15
```

Operational database:

```text
data/operational/lab.sqlite3
```

Do not delete this file if you need task/message history. Make normal filesystem
backups while the runtime is stopped.

## Cost-safe model enablement

The default runtime makes zero model API calls. Before enabling Anthropic:

- verify the exact model and current prices from Anthropic;
- configure both token rates, per-request ceiling, and total process ceiling;
- enable only the agents that need a model;
- use a dedicated API key from the environment;
- start with the smallest output limit and inspect usage after one question.

The process ledger resets on process restart; provider-console spending limits remain
an additional external safeguard and should also be configured.

## Incident response

- Leaked API key: revoke it immediately in the provider console and create a new one.
- Unexpected cost: disable the provider in `configs/agents.toml` before restarting.
- MT5 unavailable: CSV research and all stored datasets continue to work.
- Non-demo account detected: the connection is intentionally closed; switch the MT5
  desktop terminal to a broker Demo account before retrying.
- Browser microphone unavailable: use typed chat or open the dashboard in current
  Chrome/Edge and grant localhost microphone permission.
- Demo order refused: inspect quote age, spread, lot step, the environment switch,
  confirmation phrase, and MT5 AutoTrading permission. Never bypass a guard.
- Corrupt experiment: preserve it, record the failure, and create a new experiment ID.
- Runtime crash: run `runtime-once`, inspect the daily report, then restart foreground mode.

## Installed always-on mode (recommended for MT5 Desktop)

Because the MetaTrader terminal normally runs inside the signed-in Windows desktop
session, the supplied Task Scheduler installer is safer than a non-interactive Windows
Service. It starts at user logon, runs without opening a browser, and restarts the Python
process one minute after a failure:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_always_on_task.ps1
```

Remove it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_always_on_task.ps1
```

By default the runner monitors the seven major pairs on M15. You can test a different
configuration manually before installation:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_always_on.ps1 `
  -Pairs "EURUSD,GBPUSD" -Timeframe H1 -MonitorIntervalSeconds 60
```

The worker writes live heartbeats for `dashboard_worker`, `research_scheduler`,
`mt5_monitor`, and `lab_runtime`. A disconnected MT5 session makes the endpoint degraded.
The real health endpoint is:

```text
http://127.0.0.1:8765/api/health
```

Failures are always persisted to the operational journal. To additionally push a
deduplicated alert, set `AI_QUANT_ALERT_WEBHOOK_URL` to a credential-free HTTPS webhook
in the user environment before starting the scheduled task. The webhook receives health
facts only and never receives MT5 credentials or order authority.
