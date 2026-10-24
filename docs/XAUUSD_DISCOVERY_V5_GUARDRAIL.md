# V5 Monthly Guardrail Follow-up — 2026-10-24

Continuation of the No Risk FX XAUUSD extended research session. **Research-only; rejected.**

Thirty switch-off filters were evaluated on the already locked V4 extreme-continuation candidate. The filters determine eligibility for trading using *only preceding complete months* of a simulated shadow ledger, never the current or future month. Development window 2010–2017, confirmation 2018–2021, and historical diagnostics 2022–Sep 2026.

Selected solely from development/confirmation: allow signals when prior 6 months' shadow R > -2. Results:

- Confirmation 2018–21: +21.47 R and 27/48 profitable months (baseline V4 +26.22 R and 30/48).
- Previously inspected 2022–Sep 2026 diagnostic: **−1.17 R and 13/57 profitable months**, compared to V4 baseline +4.13 R and 23/57.
- Months without executed trades are not counted as profitable.
- Decision: **reject monthly gate; worse than underlying hypothesis**. Do not cherry-pick from diagnostic results.

In this session, a total of 672 ATR-bracket trials, 1,296 ATR-trailing trials, 243 neighboring-parameter tests, and 30 monthly switch-off overlays were analyzed. Six deterministic order execution tests passed. Separately, 20,000 3-month block bootstrap resamples were used as descriptive uncertainty analysis. Neither candidate nor filter satisfies profitability in every month; no live execution permitted.

The corresponding independently executable scripts, tests, diagnostic output tables, and narrative report are in the conversation's user-downloadable research archive. Project integration still requires core XAUUSD instrument support and broker-contract economics.
