# Architecture

## Design rules

1. LLM reasoning never performs numerical backtests or broker execution.
2. Market data and every experiment have immutable fingerprints.
3. Strategies emit causal signals; the engine executes them on the next bar.
4. Failed experiments and rejected strategies remain in the registry.
5. Sentinel and Aegis gates cannot be bypassed by Atlas.
6. Real and contest accounts are structurally refused by the MT5 demo gateway.
7. Strategy signals never call broker execution automatically.


## Two-layer learning architecture

The system separates proposal generation from numerical authority:

```text
Brain layer (bounded)
  Thompson selection / pair-calibrated EM / genetic proposals / optional LLM text
                              │
                              ▼
Execution layer (authoritative and deterministic)
  frozen hypothesis → Chronos → Sentinel → Aegis → research registry
```

The Brain layer may select an already-declared strategy arm, propose locked parameters,
or add qualitative commentary. It cannot calculate official performance metrics, alter a
gate, clear the kill switch, approve live trading, or call broker execution. Every evolved
parameter set is stored as an untested proposal and must enter a later campaign through the
complete evidence chain before it can become a Challenger.

Strategy selection uses a persistent Beta posterior for each
`(pair, timeframe, regime, strategy)` arm. Thompson draws are seeded from immutable
campaign and posterior state, making the mathematically exploratory choice exactly
replayable from SQLite. The posterior receives the final deterministic Quant Score only
after Aegis has recorded its decision.

Iris calibrates the three-state Gaussian HMM independently for each pair/timeframe dataset
using scaled Baum-Welch EM. Means, variances, transition probabilities, iterations, and
log-likelihood are preserved in the regime evidence.

## Components

```text
CSV / MT5 history → validation → Parquet + immutable manifest
                              │
                 Vega quality + exact dataset version
                              ▼
        Iris HMM/GMM/Bayesian/Kalman probabilistic regime
                              ▼
              Nova pre-registered falsifiable hypothesis
                              ▼
        Chronos next-bar backtest + embargoed OOS + cost stress
                              ▼
        Sentinel leakage / multiple testing / PBO audit
                              ▼
                 Aegis hard risk gates + kill switch
                              ▼
         Forge challenger/rejection → Echo factual report
                              ▼
        Append-preserving institutional registry (no auto-live)

Verified MT5 Demo → completed bars + quote + positions
                              ▼
              Regime-weighted strategy ensemble
                              ▼
                 Shadow decision + scan audit
                              ▼
               Voice dashboard + agent context
```

The complete catalog can also run as one manual `ResearchCampaign`, which invokes the
same backtest and validation pipeline for each strategy on the identical canonical
dataset and writes a research-only ranking.

The continuous institutional program is separate and idempotent by completed-bar key.
Each evidence stage has its own real task, named agent, tool/input/output contract, result,
and recorded hand-off. A restart reloads the control state, tasks, messages, and campaign.

## Agent runtime

`LabRuntime` owns one shared `TaskBoard`, `AgentMessageBus`, `ActivityJournal`,
`RuntimeScheduler`, and `SQLiteOperationalStore`. On restart it restores task and
message snapshots before accepting new work. Daily task IDs include the UTC date,
so repeated scheduler ticks cannot create duplicates.

The conversation service records the user question, marks it read by the addressed
agent, derives context from real tasks, MT5 status, monitor scans, positions, and
campaigns, then records the answer. Factual local context is answered before an
optional model. Without a configured model, deterministic truthful replies remain
fully usable.

## Voice dashboard boundary

The UI is a dependency-free Python `ThreadingHTTPServer` bound to `127.0.0.1`. Every
POST requires a random process-scoped token injected into the page. Cross-origin
preflight is rejected, static assets use a restrictive content-security policy, and
request bodies are bounded. Browser speech capabilities provide continuously rearmed
recognition after one permission click and agent-specific reply synthesis; typed chat
is always available. Recognition pauses while an agent speaks so it does not answer itself.

## MT5 demo execution boundary

`MT5DemoGateway` calls `account_info` immediately after terminal initialization and
compares `trade_mode` with `ACCOUNT_TRADE_MODE_DEMO`. Any other mode is disconnected
and audited. Continuous monitoring reads completed bars starting at position one, so
the still-forming bar is not used.

Optional manual demo orders have a separate path from monitoring. The path requires
an environment switch, an exact confirmation phrase, fresh quote, spread and volume
limits, SL/TP, broker `order_check`, and a verified cached demo-account snapshot. The
ensemble monitor has no call to `order_send`.

## Storage

- Market data: Parquet plus manifests under `data/processed`.
- Operational state: SQLite under `data/operational`.
- Experiment artifacts and registry: `data/experiments`.
- Versioned pair state: `data/intelligence`.
- Blind holdouts: `data/blind_validation` through Sentinel-authorized service calls.
- Shadow/paper observations: append-only SQLite under `data/simulation`.
- Live demo scan history: append-only SQLite under `data/monitor`.
- Sanitized demo connection/order audit: append-only SQLite under `data/demo`.
- Cross-strategy comparisons: JSON/Markdown under `data/campaigns`.
- Continuous research registry: SQLite under `data/institutional`.
- Frozen institutional datasets, experiment records, and reports: `data/institutional`.
- Daily reports: Markdown under `data/reports`.

## Model boundary

`AgentModelProfile` separates identity from provider/model choice. Providers receive
sanitized prompts, declared context, allowed-tool names, timeouts, output limits, and
explicit pricing. API keys are read by the adapter from the process environment.

The Anthropic adapter follows the Messages API shape with `x-api-key`, the versioned
API header, system text, user messages, and returned input/output usage. No agent has
permission to trade live.
