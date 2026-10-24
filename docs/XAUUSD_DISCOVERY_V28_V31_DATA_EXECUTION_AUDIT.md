# XAUUSD Discovery 28–31 — Source M1 integrity and stop execution audit (2026-10-24)

**RESEARCH-ONLY, REJECT TRADING PROMOTION. No new profitable-every-month strategy discovered.**

The user-supplied `Gold data.zip` SHA256 is `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. It contains exactly **5,936,421 M1 rows** across 17 annual JSON files, from Jan 2010 to Sep 20 2026. The previously frozen derived XAUUSD M15 cache SHA256 is `4e1e39e433718da0bd92f48b0f36fc1c55339ca98b699735d8379a57a8640d71`.

These are **independent quote integrity and execution sensitivity audits**, not parameter optimization or new out-of-sample validation. The earlier dev/confirm/2022+ periods were all already inspected. Baseline estimated execution = real data source's Bid/Ask OHLC, nominal adverse slippage $0.10 per side and fee $0.05 per trade, no verified broker swaps, financing, margin, market impact, or lot-to-ounce translation. All results per **max 1 troy ounce**, not account ROI.

## D28 — 12 minute-quality historical robustness replays

There are **397,299 M15 bars**, **6,186 (1.56%)** built with fewer than 15 source M1 observations:

| Historical era | M15 bars | Incomplete M15 bars | % |
|---|---:|---:|---:|
| 2010–2017 | 191,223 | 4,832 | 2.53% |
| 2018–2021 | 94,558 | 977 | 1.03% |
| 2022–Sep 2026 | 111,518 | 377 | 0.34% |

3 previously locked, **unapproved** algorithms (V4 extreme z-continuation; V11 previous-week upside breakout; monthly regime Policy10) × 4 fixed completed-signal-bar quality modes: unchanged, 15/15 minutes for current closed signal bar, and 4/64 prior+current closed bars complete. No optimizer selected from historical diagnostic results. All modes are causal **at signal completion**; any rule using whether the *future entry* M15 candle has all 15 source minutes at decision time would leak future information.

Historically viewed 2022–2026 V11: **28/343** closed trades overlapped at least one incomplete M15 bar. These accounted for +$434.81/oz realized combined, while the other 315 trades totaled −$185.16/oz. **This is not evidence those profitable trades are false:** overlapped positions lasted **66.4 M15 bars on average** vs 32.3 for non-overlapped positions; holding-time confounding increases encounter probability. Dropping completed-signal-bar exceptions did not achieve monthly or annual stability; never treat such filtering as newly confirmed alpha.

## D29 — exact cross-check of all 17 raw files

Independently reassembled **all 397,299** M15 candles, bid and ask open/high/low/close + minute counts, with **zero discrepancies** versus the prior derived pickle and **zero duplicate raw minute timestamps**. The source `v` is a nonzero fractional vendor-specific quantity; its units are not authenticated. In the M15 cache `ts` is merely the number of observed source M1 rows per bar, not tick volume.

928 M15 bars have no source quote at the theoretical quarter-hour open; in 162 the first observation is >=5min delayed; 1,820 have no observation in minute 14. This is source feed timing, not measured broker order latency.

## D30 — actual entry quote observation delays

Joined **2,991** rows from the three frozen strategy ledgers to first-observed M1 quote times. Only **3 entries** across all those ledger rows happened in delayed-opening M15 bars, 2 with >=5-minute delay. Over inspected 2022+ era: V11 **zero**, Policy10 **zero**, V4 **one** delayed entry, a -$21.47/oz trade. Therefore late first quote at the entry bar is **not** driving the concentration of V11 returns described above.

## D31 — minute-level stop-market gap audit

Reconstructed the exact M15 trailing-stop trajectory, including the dynamic ATR threshold, of all **2,991** previously closed trades: recovered their initial reported PnL to within $0.00002 each. All 2,991 had stop exits. Searched the original M1 Bid lows / Ask highs for the first minute that touched the original stop. If the corresponding M1 minute opened across the stop, used the worse *observed first-minute executable quote* instead of implicitly filling at the M15 stop level.

**51** stop exits got incrementally worse, with total extra $3.65125/oz summed across **three partly overlapping strategy ledgers** (NOT one account!). Observed 2022+ additional losses: V4 **$0.069375/oz**, V11 **$0**, Policy10 **$0**. This checks only *observed M1 open-through-stop gaps*: cannot recover prices inside missing minutes, intra-M1 tick trajectories, or broker liquidity/slippage/swap. No broker approval is implied.

## Reproducibility / lock safety

Standalone Session10 research archive is supplied in the project conversation as `no_risk_fx_discovery_session10_2026_10_24.zip` (does **not** duplicate the user's original 149MB compressed raw ZIP). It includes derived M15 cache, frozen dependencies, all 17-file audit logic, per-bar quote timing, 12-strategy-sensitivity tabulations, 2,991 reconstructed stops, trade exposure tables, explanation, SHA256 manifest and tests.

**14/14 tests passed locally, and 14/14 also passed after extraction in a separate fresh directory; 10/10 selected generated output SHA256 files matched exact prepackaged copies.** Re-running raw M1 checks requires user's original ZIP via the `GOLD_ZIP` environment variable. Critically, **the October 24 frozen November 2026 forward shadow-only source and lock were checked unchanged**, and all trade/order sending remains blocked.

**Decision:** no candidate is profitable in all historical months; no new promotion. More historic filtering of these familiar data would not produce independent validation. For the next prospective study, obtain missing Sep21–30 and verified Oct/Nov 2026 Bid/Ask quotes, broker-specific gold point/lot/contract/swap/margin specs, and a higher quality independent source for missing-minute price path resolution.

The native XAUUSD code is still staged on this research branch and native GitHub CI success has **not** been verified.
