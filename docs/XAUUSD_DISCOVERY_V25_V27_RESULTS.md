# XAUUSD Research — Discovery 25–27 and first fully future-month freeze (2026-10-24)

**Status: research-only, no trading approval, no all-month-profitable strategy found.**

Historical input: user's 397,299 M15 bid/ask gold quotes, 2010-01-01 through **2026-09-20 23:45 UTC** (September 2026 incomplete). Earlier project sessions examined every historical era repeatedly. Do **not** present 2018–2021 or 2022–2026 as pristine untouched blind tests. P&L below is hypothetical US dollars per **at most one troy ounce**, after source Bid/Ask and nominal added $0.10 per side + $0.05 per trade, excluding verified broker swap, commissions, contract and leverage.

## Discovery 25: monthly decision phase-rotation falsification

Frozen, **unapproved** monthly policy 10 from Discovery 22/24 chooses V11 prior-completed-week upside breakout when the last three completed months have positive gold-price trend; otherwise chooses V4 192-M15-bar extreme continuation. We enumerated all **198 nonzero cyclic time shifts** of the selector's month choices, preserving allocation counts. These shifted schedules are **noncausal placebo controls**, NOT implementable alternative models or calibrated significance tests.

| Interval | Original USD/oz | Winning complete months | Fraction of phase shifts with net >= original |
|---|---:|---:|---:|
| Development 2010–17 | +123.27 | 41/96 | 22.1% of 95 |
| Confirmation 2018–21 | +210.95 | 30/48 | 25.5% of 47 |
| Previously viewed 2022–partial Sep2026 | +449.35 | 28/56; incomplete Sept excluded | 7.1% of 56 |

No development promotion gate passed. These comparisons do not demonstrate repeatable predictive alpha.

## Discovery 26: SHA256-locked forward shadow-only protocol

**Critical chronology:** The current protocol date is **2026-10-24**. The dataset stops on **2026-09-20**. September 21–30 and October prices are absent. A complete October 2026 result cannot be called **fully prospective from 24 October**, because most of that month has already occurred.

Therefore the **first fully new calendar month for this preregistered shadow experiment is November 2026**, not October. November must finish and new verified historical Bid/Ask observations covering all weekdays **2026-09-21 to 2026-11-30** must become available before scoring. The quote-data validator requires at least 64 M15 bars covering both early and late UTC per weekday, sound monotone timestamps, separate bid/ask OHLC envelopes, no overlapping baseline bars and month-end coverage. This is a conservative quality proxy, **not a verified broker session calendar**.

The shadow protocol hashes all frozen strategy source dependencies, locked policy selection record, derived M15 cache, and guard logic; it rejects mismatched or overwritten lock versions and contains **no order-sending capability**. It permits only descriptive November score of frozen illustrative policy 10 and V4/V11 baselines, with trade fills modeled by the existing retrospective bid/ask simulator. It still does not approve a strategy.

Auditable lock record:
- baseline trusted derived M15 SHA256: `4e1e39e433718da0bd92f48b0f36fc1c55339ca98b699735d8379a57a8640d71`
- locked selector engine SHA256: `12e94d5726f29676d15a312eeca049089645d0bc7c44947b367dc05954bcfbfd`
- lock's failed-development-selection SHA256: `b4436589f0b36b44ad2b08b917768ab91577785f46228db967062d33621779c5`
- SHA256 of downloadable Session9 ZIP: `2d6c0874af1a9ff1960e2fa1add6cf6c5908eb3b98836909bb28ff8c4114fe60`

**Actual state:** No new post-Sep20 bid/ask data was provided, so **no November result was computed**. No market forecasts or synthetic market prices were substituted.

## Discovery 27: entry latency falsification

Without tuning stops or signals, used predetermined executable entry delays of **1, 2, 4 and 8 M15 bars** (15, 30, 60 and 120 minutes after completion of the original signal). Suppressed signals stale across data gaps or month boundaries. **12 sensitivity conditions** for V4, V11 and unapproved monthly policy 10.

| Historical result, USD/oz | Next M15 | 30min | 60min | 120min |
|---|---:|---:|---:|---:|
| V4 2018–21 | +308.19 | +291.11 | +201.76 | +117.68 |
| V4 viewed 2022–Sep26 | +17.00 | +93.12 | **−151.96** | **−58.10** |
| V11 2018–21 | +0.70 | **−82.10** | **−141.12** | **−151.91** |
| V11 viewed 2022–Sep26 | +249.65 | +142.76 | **−194.59** | **−349.36** |
| Policy 10 2018–21 | +210.95 | +149.76 | +76.02 | +52.96 |
| Policy 10 viewed 2022–Sep26 | +449.35 | +289.11 | +6.19 | +38.04 |

**Interpretation:** Strong historical dependence on fast execution, especially V11. Do not select a 'best' delay based on the already-inspected 2022+ diagnostics. Simulated broker execution delay is not the same as realized broker slippage.

## Reproducibility and next blocker

**19/19 unit tests passed.** The Session 9 full research archive in the project conversation (22 members incl. M15 derived quote data and complete code) was extracted and independently rerun; all five compared CSV/JSON SHA256 outputs were identical, with 19/19 tests passing in replay. Source-price ZIP and credentials were NOT committed to GitHub. The existing AI Quant Lab `main` still does not have this research merged, and native GitHub CI completion has not been verified.

**Decision: reject trading promotion**. Require broker XAUUSD contract size, point size, margin, realistic swaps and commissions, audited September/October/November quote data, and first new complete calendar-month November shadow scoring with absolutely no post-freeze retuning. There cannot be a guarantee of a profitable every month strategy.
