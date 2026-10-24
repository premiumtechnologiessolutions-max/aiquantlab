# XAUUSD Quant Discovery — Research update (2026-10-24)

Status: **research only; no trading approval**. This branch remains a staging branch and the core lab's seven-pair `ForexPair` schema has **not** yet been extended to gold.

The user supplied 17 yearly XAUUSD bid/ask JSON files covering 2010-01-01 through 2026-09-20 (~5.95m M1 prices, 397,299 aggregated M15 bars). Standalone Python studies were run with next-bar executable bid/ask fills, adverse stop-first bars, slippage, spread and a nominal fee. No financing in headline runs. Periods: 2010–17 discovery, 2018–21 confirmation, 2022–2026 historical diagnostic, *not pristine blind OOS* because prior rounds inspected it.

- Experiment 3: 672 fixed ATR bracket candidates across 13 families; zero net-positive in discovery on the initial-stop-risk R basis.
- Experiment 4: 1,296 ATR-trailing variants; 56 eligible discovery candidates and 7 of the top 50 passed confirmation gates. All 7 were variations of the same extreme z-score continuation hypothesis, not independent systems.
- Selected: 192 M15 lookback, z-score threshold 3.25, high-volatility filter, initial stop 5x ATR(64), trailing stop 4x ATR(64), maximum hold 576 bars. Locked without using 2022+ diagnostic results.
- 2010–17: 454 trades; +0.61 R; 40/96 positive months; 4/8 years.
- 2018–21: 179 trades; +26.22 R; 30/48 positive months; 4/4 years.
- 2022–Sep 2026: 229 trades; +4.13 R; 23/57 positive months; 3/5 years; profit factor 1.058; +$17.00 **per troy ounce** before financing. At 3x tested slippage/fee, −3.25 R.
- 243 nearby parameter variants tested descriptively; median 23/57 positive diagnostic months. A 20,000-repetition monthly block bootstrap interval for diagnostic total R was approximately −21.7 to +32.0.
- Hypothetical financing of $0.25/oz per elapsed 24h changes the 2022+ absolute P&L to about −$20.43/oz (not a broker swap quote).
- Six executable synthetic order-fill unit tests passed, including the zero-trade case. The simulator was amended to skip stale signals after market gaps >30 minutes.

**Decision:** Do not promote. No robust all-month-profit strategy was found; even the selected candidate is sensitive to costs and fails monthly consistency. Do not rerank on previously examined diagnostic data. The user-facing session artifact includes source scripts, test suite, 1,296 trials, 243 neighbor trials, monthly/annual tables, and explicit research caveats.

Next engineering steps: instrument-type support for XAUUSD in core lab; symbol contract metadata and broker-specific swap, spread, timezone, and execution; import audit; genuine prospective shadow verification. Never claim a month-profit guarantee.
