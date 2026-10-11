# Institutional Research V4

This document states what V4 actually executes and what still needs licensed data.

## Automatic evidence chain

One newly completed bar per pair/timeframe creates one durable, idempotent campaign:

1. **Vega — Data Intelligence:** reads completed MT5 bars, checks chronology, duplicates,
   calendar-aware gaps, outliers, volume, and spread; then freezes an exact SHA-256 version.
2. **Iris — Regime Analysis:** calibrates a causal three-state Gaussian HMM with scaled
   Baum-Welch EM on the exact pair/timeframe dataset, then blends it with a two-component
   volatility GMM, Bayesian adjacent-window change evidence, a local-linear Kalman slope,
   return autocorrelation, and spread stress into a normalized regime distribution.
3. **Oracle — Capability Audit:** records missing macro and cross-asset inputs and excludes
   risk-on/risk-off claims when those feeds do not exist.
4. **Nova — Hypothesis:** a replayable Thompson sampler first selects an eligible strategy
   arm for the exact pair/timeframe/regime. Nova then locks its parameters, falsifiable claim,
   economic rationale, compatible regime, and rejection criteria before OOS is viewed. An
   optional bounded LLM may draft only the qualitative fields; it cannot change the arm or
   parameters.
5. **Chronos — Validation:** runs cost-aware next-bar tests, an embargoed 60/40 OOS split,
   purged walk-forward validation, neighboring-parameter tests, temporal/regime slices,
   and transaction-cost stress.
6. **Sentinel — Audit:** records one-bar execution lag, exact dataset identity, purge and
   embargo, all attempts, multiple-testing adjustment, and probability of overfitting.
7. **Aegis — Risk:** can reject for data quality, liquidity/spread, drawdown, OOS stability,
   Quant Score, or emergency stop. High-volatility/transition regimes cut size by 35%.
8. **Forge — Evolution:** registers the tested candidate, updates the selected arm's Beta
   posterior from the final Quant Score, and may create one deterministic crossover/mutation
   child from validated same-arm Challengers. The child is an untested proposal, not a
   Challenger, until a later campaign passes it through Chronos, Sentinel, and Aegis. Forge
   never promotes to Paper, Champion, or live trading automatically.
9. **Echo — Report:** writes a factual Markdown report distinguishing evidence from proposal.

Atlas owns the root task. Each transition creates a durable hand-off message to the next
Agent. Failed stages and trials remain visible rather than being deleted.


## Brain versus execution authority

The execution layer is the sole authority for backtests, annualized Sharpe/Sortino,
Bonferroni correction, risk limits, size throttles, and every gate. Annualization uses the
actual bars-per-year mapping for M1, M5, M15, H1, H4, and D1. Multiple-testing adjustment is
explicit and uses a de-annualized test statistic before applying Bonferroni.

The Brain layer consists of deterministic learning/search components plus optional model
text:

- persistent Thompson sampling by `(pair, timeframe, regime)`;
- pair/timeframe-specific Baum-Welch HMM calibration;
- deterministic genetic crossover/mutation proposals;
- optional budgeted Nova hypotheses and Sentinel/Echo commentary.

Model output is non-authoritative. It cannot change a metric, risk decision, locked
parameter, kill switch, or live authorization. Provider failure or budget exhaustion falls
back to the deterministic path.

## Quant Score

The score uses fixed declared weights:

- 20% risk-adjusted return
- 15% drawdown quality
- 15% out-of-sample stability
- 15% regime robustness
- 10% parameter stability
- 10% cost robustness
- 10% statistical significance
- 5% execution feasibility

Advanced evidence includes Calmar, drawdown duration, tail ratio, CVaR, skewness, turnover,
exposure, average holding period, capacity proxy, slippage sensitivity, Deflated Sharpe,
multiple-testing-adjusted p-value, and estimated probability of backtest overfitting.

Passing this score authorizes research consideration only. `approved_for_paper` and
`approved_for_live` remain false in every automatic V4 decision.

## Strategy coverage

V4 has 16 directly executable causal strategies, including time-series momentum, Kalman
mean reversion, and volatility breakout. The institutional catalog contains 35 blueprints
covering trend, reversion, statistical arbitrage, volatility, cross-sectional,
microstructure, and portfolio families.

Every blueprint declares one of four states:

- `executable`
- `research_engine`
- `requires_aligned_assets`
- `requires_external_data`

Cointegration diagnostics and inverse-volatility risk parity are implemented research
engines. Johansen/PCA/HRP, order-book/trade-flow methods, funding/open-interest,
liquidations, options, and macro-dependent methods do not claim executable status until
the required aligned or licensed feeds are connected.

## Operator controls

The Quant Command Center exposes Start, Pause, Emergency Stop, and Reset. Control state is
stored in SQLite. Reset clears the emergency latch but deliberately leaves research paused;
the operator must press Start again.

Clicking an Agent card displays its role, task progress, result or error, tools, input and
output contract, and recent inbox/outbox hand-offs. The browser refreshes read-only state;
it does not invent activity.

## Safety boundary

V4 is a Demo/research platform, not an autonomous investment product. Real and contest MT5
accounts remain blocked. Strategy signals cannot send broker orders. The separate manual
Demo order form is disabled by default and still requires explicit safeguards and the exact
human confirmation phrase.
