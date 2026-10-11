# Voice Dashboard and MT5 Demo

## Purpose

The local dashboard lets the user speak or type to Atlas, Vega, Nova, Chronos,
Iris, Sentinel, Aegis, Oracle, Echo, and Forge while viewing real persisted tasks,
the latest market scan, campaign evidence, and sanitized MT5 Demo state.

It is not a public website. It binds to `127.0.0.1`, does not need a cloud account,
and has no dependency on a paid language model.

## One-time setup

1. Install MetaTrader 5 from the chosen broker on Windows.
2. Create and open a broker **Demo** account in the desktop terminal.
3. Enable the symbols in Market Watch and download enough chart history.
4. Install AI Quant Lab using the README commands.
5. Start:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_voice_dashboard.ps1
```

The terminal can use its already logged-in account, in which case the login fields
may be left empty. If credentials are entered, they exist only in the child process
environment until the script exits.

## Browser voice use

- Open the automatically launched Chrome or Edge page.
- Allow microphone access for localhost.
- Press the microphone button once to arm continuous listening.
- Call an agent by name; recognition restarts after silence and after spoken replies.
- The named agent stays active for follow-ups such as `ليش؟`, `وبعدين؟`, and `عيدها`
  until another agent is called by name.
- The recognized sentence is shown before it is sent.
- The answer is displayed and optionally read in that agent's distinct voice profile.
- Disable **اقرأ جواب الـAgent بصوت مرتفع** when audio is not wanted.
- Disable **استماع مستمر** to return to one-question mode.

Browser security requires the first microphone activation to be a real user click.
After that click, the dashboard can keep rearming recognition while the page remains open.
When Windows exposes multiple Arabic TTS voices they are distributed across agents;
otherwise each agent still has a different rate and pitch.

Examples:

```text
يا Atlas شو وضع الفريق؟
يا Vega هل حساب MT5 موصول؟
يا Iris شو حالة السوق وآخر إشارة؟
يا Aegis في صفقات مفتوحة؟
يا Nova شو الاستراتيجيات وآخر تجربة؟
```

## Continuous monitoring

The dashboard worker runs the persisted runtime and, by default, attempts one bounded
market scan every 30 seconds. Each scan:

1. verifies or reuses the Demo connection;
2. reads completed bars, excluding the current forming bar;
3. runs the declared causal strategy ensemble;
4. weights compatible strategy families for the detected regime;
5. records long/short votes and a consensus;
6. appends a Shadow decision and scan audit;
7. exposes the result to agents and the UI.

Monitoring never sends an MT5 order. Run without recurring scans when needed:

```powershell
ai-quant-lab voice-dashboard --no-auto-monitor
```

## Demo-order arming

Manual demo orders are intentionally locked. For a controlled session only:

```powershell
$env:AI_QUANT_ENABLE_DEMO_ORDERS = "true"
$env:AI_QUANT_DEMO_MAX_VOLUME = "0.10"
ai-quant-lab voice-dashboard
```

Open the advanced panel, provide volume and positive SL/TP distances, then type the
exact phrase `DEMO ONLY`. The gateway still checks account mode, quote age, spread,
broker volume limits and steps, account permission, and MT5 `order_check`.

Return to the locked default after the session:

```powershell
Remove-Item Env:AI_QUANT_ENABLE_DEMO_ORDERS -ErrorAction SilentlyContinue
Remove-Item Env:AI_QUANT_MT5_PASSWORD -ErrorAction SilentlyContinue
```

## Broker suffixes

If the broker calls EURUSD something like `EURUSD.a` or `EURUSDm`, set only the suffix:

```powershell
$env:AI_QUANT_MT5_SYMBOL_SUFFIX = ".a"
```

## Troubleshooting

- **MT5 package unavailable:** run on Windows with Python 3.12 and reinstall the project.
- **Initialization failed:** open the desktop terminal, confirm its path, login, server,
  and internet connection.
- **Non-demo blocked:** this is expected protection; log into a genuine Demo account.
- **Not enough bars:** open the symbol chart and scroll/download history, or reduce the
  monitor lookback while keeping at least 60 bars.
- **Microphone unavailable:** type into the same chat; no agent feature is lost.
- **Permission denied:** click the lock/site icon next to `127.0.0.1`, allow the
  microphone, refresh once, and press 🎙.
- **Wide/stale quote:** wait for an open, liquid market instead of weakening limits.
- **Order check rejected:** read the broker comment and correct permission, volume,
  symbol, stops, or filling requirements; do not bypass the check.

No passing research result is a profit guarantee. Leave real-money trading outside
this application until a separately reviewed production design and adequate empirical
evidence exist.
