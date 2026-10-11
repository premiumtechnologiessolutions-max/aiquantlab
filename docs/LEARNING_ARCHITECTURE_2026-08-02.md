# Learning Architecture Upgrade — 2026-08-02

## Implemented

- Corrected Sharpe and Sortino annualization for every supported timeframe.
- Added explicit Bonferroni-adjusted p-values using a de-annualized test statistic.
- Replaced fixed/round-robin strategy choice with replayable Thompson sampling and durable
  Beta posteriors per pair, timeframe, regime, and strategy.
- Replaced shared fixed HMM constants with pair/timeframe-specific scaled Baum-Welch EM.
- Added deterministic Forge crossover/mutation and a separate untested proposal lifecycle.
- Added optional bounded Anthropic-backed Nova, Sentinel, and Echo assistance with strict
  budgets and deterministic fallback.
- Added real component heartbeats, `/api/health`, deduplicated HTTPS operational alerts,
  and Task Scheduler installation scripts with restart-on-failure behavior.

## Invariants preserved

- Official metrics and gates remain deterministic.
- Hypotheses and strategy parameters are frozen before OOS evidence.
- No model or learning component can clear the kill switch.
- `live_trading_authorized` remains false.
- No strategy-selection, model, or research path calls `order_send`.
- Human confirmation remains mandatory for the separate guarded MT5 Demo order form.

## Deliberately deferred

Atlas LLM prioritization across pairs/timeframes was not enabled. A future implementation
should first define a deterministic utility function and constraints so the model can only
rank already-eligible work, never alter constitutional gates.
