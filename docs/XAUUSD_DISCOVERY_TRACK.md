# XAUUSD autonomous discovery — research track (2026-10-24)

Status: **research staging only; no historical backtest has been run**.

## Verified repo constraints
- Current `ForexPair` is a seven-FX-pair Literal in `src/ai_quant_lab/config.py`; XAUUSD is not yet accepted by canonical ingestion.
- The existing catalog supports 16 executable strategies; the existing campaign, walk-forward, mutation and institutional gates are reusable **after** XAUUSD data/schema/valuation integration.
- The uploaded "Gold Daily Fibo M15" Pine source is available in the originating conversation; its strategy should be translated and checked against TradingView signals before enabling in the catalog.
- The "Tail/Ghost" excerpt consists of dashboard/statistics statements only; it is **not** a reproducible trading strategy without entry/exit logic.
- No XAUUSD historical OHLCV/spread dataset was available in the conversation runtime.

## Candidate families (all UNTESTED on gold)
1. Prior-day Fibonacci close crossing at 0.382 / 0.5 / 0.618 / 0.786, separately testing reversal and continuation and first-touch priority.
2. Persistent swing-level Fibonacci with *causally confirmed* pivots and invalidation after N consecutive closes; prevents use of future pivots.
3. Donchian channel breakout on gold, adaptive ATR or realized-volatility filter.
4. Variance-ratio regime switching between time-series momentum and z-score mean reversion.
5. Session-specific volatility breakout and opening-range reversal.
6. Kalman latent-level residual extremes with volatility-normalized exits.
7. Null baselines: random-side trades with matched holding durations, always-flat, buy-and-hold.

## Translation requirements for prior-day Fibo
- Reference previous **completed** daily session's OHLC, with explicit broker-day timezone and Sunday candle policy.
- Signal at completed M15 bar t; trade no earlier than next executable quote/bar t+1.
- The Pine script uses close[1]/close[2] for signals and prioritizes 38.2 -> 50 -> 61.8 -> 78.6. Reverse=true by default.
- Preserve per-direction, per-level daily flags; verify reset at the start of a *broker* day, not midnight UTC by accident.
- Pine SL/TP based on the historical signal close rather than actual fill; reconcile fills and test both exact-ported logic and execution-corrected variant.
- Specify symbol digits, tick size, point value, contract size, spread and commissions per broker; do not equate "$" distance and trading PnL.

## Required evidence gates
1. Confirm data integrity: minute coverage, holidays, duplicate timestamps, split/session timezone, broker rollovers, stale bars, spread.
2. Lock a blind final test span before parameter search; use purged/embargoed expanding walk-forward folds.
3. Stress entry delay, spread/slippage multipliers, costs and adverse intrabar SL-before-TP ambiguity.
4. Candidate ranking: OOS net PnL, Sharpe/Sortino, max drawdown, profit factor, minimum trade count, annual PnL across calendar years.
5. Quantify multiple-testing effects and parameter sensitivity; keep every failed candidate in registry.
6. Only promote to shadow research if hard gates pass. Do not claim guaranteed profit or run live orders.

## First implementation dependency checklist
- [ ] Extend instrument schema from FX-only `ForexPair` to instrument identity supporting XAUUSD **without changing forex pip economics**.
- [ ] Add gold tick/contract multiplier and calibrated spread/commission semantics to evaluator.
- [ ] Import real broker XAUUSD M1; aggregate non-leaking M5/M15/H1/H4/D1.
- [ ] Register Fibo variants and test deterministic equivalence.
- [ ] Add automated walk-forward campaign and annual scorecard.
- [ ] Import full Tail/Ghost trade logic if provided.
