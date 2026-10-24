# XAUUSD Discovery 22–24: causal monthly meta-selector and stress (2026-10-24)

**RESEARCH-ONLY. NO CANDIDATE PROMOTED. NO LIVE OR DEMO ORDERS.**

Historical source: user's 17-year bid/ask gold archive, previously aggregated into **397,299 XAUUSD M15 candles (2010-01-01 through 2026-09-20)**. September 2026 is partial. Research simulation uses executable next-M15 bid/ask open, conservative stop-first intrabar execution, $0.10/oz adverse slippage per side, $0.05/oz nominal roundtrip fee, spread limit $5/oz, stale signal limit 30 minutes and **one position maximum**, at up to 1 troy ounce; no verified broker contract, margin or financing in baseline.

The two strategies were **locked before** this session:
- V4: 192-bar z-score 3.25 extreme-move continuation with elevated volatility gate; initial 5 ATR(64) stop, 4 ATR trail, 576 M15 bars maximum holding.
- V11: previous completed-week high breakout, long only; 5 ATR stop, 4 ATR trail, 288 M15 bars max.

## 15 monthly selection policies: development 2010–17, confirmation 2018–21

Month m selects one strategy using only months **earlier than m**. Strategies' *independent shadow* month-end USD P&L are available as lagged signals; a live selected trade retains its original stop and strategy even if month changes. Tested 15 fixed policies: V4-only, V11-only, trailing 3/6/12/24-month P&L winner, 6/12-month risk-adjusted winner, 6/12-month positive-or-cash gates, 3/12-month gold-price trend switch, monthly realized-volatility switch, 6/12-month both-positive-or-cash gates.

**A priori development gate** was >$0 net, >=48 of 96 profitable months, >=5 of 8 profitable years; **0/15 passed**, so do not promote any. Policy 10 (three-full-month gold trend switch) is an illustrative predeclared rule only, not an approved or retrospectively selected champion. It chooses V11 after a positive previous three-complete-month price trend, otherwise V4, with initial four months in cash.

| Policy | 2010–17 net / positive months / positive years | 2018–21 net / positive months / positive years | inspected 2022–Sep2026 net / positive months / positive years |
|---|---|---|---|
| V4-only | −$26.24 / 37 of 96 / 3 of 8 | +$308.19 / 30 of 48 / 4 of 4 | +$17.00 / 23 of 57 / 3 of 5 |
| V11-only | +$76.49 / 43 of 96 / 4 of 8 | +$0.70 / 21 of 48 / 2 of 4 | +$249.65 / 28 of 57 / 3 of 5 |
| 3-month gold trend | +$123.27 / 41 of 96 / 5 of 8 | +$210.95 / 30 of 48 / 4 of 4 | +$449.35 / 28 of 57 / 3 of 5 |

The first 56 **fully completed** months Jan 2022–Aug 2026 yield **28/56** positive months for the illustration. September 2026 is a partial month with zero additional simulated P&L; it must not be misrepresented as a complete negative/flat September.

**Annual weakness of policy 10:** 2010 −$24.52, 2015 −$66.79, 2017 −$10.77, **2022 −$153.81**, partial 2026 −$5.16 (2018–21 positive each year and 2025 +$383.52). Even a profitable aggregate has major losing years. Figures are for fixed maximum **one ounce**; not account ROI.

## 90 execution/financing stress scenarios (15 policies × 3 fee tiers × carry on/off)
Quote spread from actual bid/ask remains charged in every scenario, while *additional* slippage + nominal fee scale by 1×/3×/5×. Hypothetical carry test: $0.25 per ounce per elapsed 24 hours (NOT a verified broker swap quote).

Illustrative policy 10 in previously inspected 2022–Sep2026: **+$449.35** at 1× and no carry; +$404.10 with hypothetical carry; +$295.25 at 3× no carry; +$141.15 at 5× no carry; +$95.90 at 5× plus synthetic carry. Historical positivity does not override the failed development gate or repeated holdout exposure.

## 150 preseeded monthly random-choice controls; descriptive only
For policy 10, random control fraction with net result >= policy 10: development 22.67%; 2018–21 confirmation 22.00%; inspected 2022+ 10.00%. Not calibrated p-values, not evidence of persistent edge and not corrected for repeated research selection.

20,000 circular 3-month-block resamples from the 56 inspected completed months yield approximately **−$132 to +$1,130** for policy 10's historical total; this range includes losses and is not a forecast.

## Reproducibility / engineering
- **11/11 synthetic and real-quote unit tests passed**: no future month usage, completed-three-month regime indexing, no-trade warmup, zero-trade months, single-account nonoverlap, position cost/carry, frozen development rejection, and **real-data future-price mutation does not change earlier V4/V11 signals**.
- Independently extracted 31-file Session 8 ZIP from the user chat was replayed: all 5 commands passed and **13/13 analytical output file SHA256 hashes and the generated report were identical**.
- Session 8 deliverable includes self-contained Python source, 397,299-row trusted derived M15 quote cache, all monthly decisions and trade ledgers, 15-policy table, 90 stress results, 150 random controls, annual/completed-month scorecards, tests and SHA256 manifest.
- Staged XAUUSD branch's native integration CI is **not claimed verified**. All this session's research ran in standalone bid/ask code and never connected to an order API.

**Decision:** 0 candidates meet annual/monthly stability gates; no profit-every-month claim. New incoming **October 2026 full-month** bid/ask history is needed for the first forward evaluation after the prior dataset's Sep 20 end date. Pre-register unmodified candidate/contract specs, and verify real broker spread/swap/margin/tick/lot mechanics before any further risk approval.
