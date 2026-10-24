# Discovery 20–21: Causal XAUUSD exposure sizing and monthly cost stress (2026-10-24)

**RESEARCH ONLY — NO APPROVAL FOR LIVE TRADING.** No strategy was profitable in every month or every year.

## Reproducible session
The user's existing 397,299 completed M15 bid/ask candles (2010–2026-09-20) were used in a standalone replayable Python experiment. **16 historical simulations** were run: two *previously locked* systems (V4 extreme-price continuation and V11 completed prior-week breakout), each under eight entry-time exposure policies. All exposure decisions are based only on closed-bar realized ATR (2048 M15 median lagged) and/or last 20 **closed** trades; each entry is at most one troy ounce, not broker lots. The existing entry/exit/trailing logic was not reoptimized. Executable next-bar ask/bid entry, conservative intrabar stops, observed bid/ask spread, $0.10/oz per-side hypothetical slippage and $0.05/oz roundtrip fee.

- Policy zero, fixed one ounce, matched **all** previous Session 6 month-end USD/oz results to floating-point precision (<1.5e-14 maximal monthly mismatch).
- 2010–17 is the only *development policy selection* window. 2018–21 is temporal confirmation of the overlay conditional on the already-researched base systems. 2022–Sep2026 is **repeatedly inspected**, not independent OOS.
- The weak development-only selector preferred V4 inverse ATR exposure capped 0.25–1 oz and V11 0.25 oz during above-reference volatility. **The selector is illustrative and not a strategy promotion gate.**

| System/policy | 2010–17 net $ / positive months | 2018–21 net $ / positive months | 2022–Sep26 net $ / positive months | Recent monthly peak-to-trough drawdown |
|---|---|---|---|---|
| V4 fixed 1 oz | −26.24 / 37 of 96 | +308.19 / 30 of 48 | +17.00 / 23 of 57 | $292.61 |
| V4 capped inverse ATR | +4.88 / 41 of 96 | +244.72 / 30 of 48 | +94.76 / 25 of 57 | $219.19 |
| V11 fixed 1 oz | +76.49 / 43 of 96 | +0.70 / 21 of 48 | +249.65 / 28 of 57 | $282.17 |
| V11 quarter-size high volatility | +72.92 / 45 of 96 | +1.86 / 21 of 48 | +223.20 / 26 of 57 | $151.42 |

Dollar amounts are USD P&L for **up to one ounce**, not portfolio returns, and skip broker swap/margin. V4 sizing **did not fix** 2022 and 2025 calendar-year losses; V11 sizing **did not fix** 2018, 2021, 2022, partial 2026 losses. V4 development 3/8 winning years means weak selection is not sufficient to claim annual robustness.

## Sensitivity, financing and causality
**24 further fixed-policy cost/financing runs**: 2 systems × constant vs development-selected × 3 fee/slippage stress tiers (1×/3×/5×) × financing OFF/on. Historical bid/ask spread remains charged; only *additional* execution costs are multiplied. Financing on means hypothetical $0.25 per ounce held per elapsed calendar day, accrued into monthly open-position liquidation values; not a verified MT5 swap.

- V4 capped-inverse ATR recent net: +$94.76 at 1×, **−$2.81 at 3×**, −$100.37 at 5× costs, excluding carry. At 1× plus hypothetical carry: +$62.53. Result remains fragile.
- V11 quarter-high-vol recent net: +$223.20 at 1×, +$114.60 at 3×, **+$6.00 at 5×**, excluding carry. At 5× plus hypothetical carry: **−$21.28**. Profitable months still only 26/57 at normal costs.

**Seven deterministic tests passed:** correct size/limit, prefix invariance (future changes do not alter past equity), financing never creates profit, increasing fees cannot improve unchanged trades, no phantom profitable zero-trade months, and development policy ranking remains unchanged if all post-2017 scores are maliciously replaced.

The **24-file complete research archive**, including derived M15 quote cache, standalone scripts, 16-policy and 24-stress ledgers, monthly and yearly tables, pytest tests and SHA256 manifest, is delivered in the project conversation as `no_risk_fx_discovery_session7_2026_10_24.zip`. It was extracted into a *fresh* directory: **7/7 tests passed and 8/8 generated result/report SHA256 hashes matched exactly**. Source-price ZIP and private credentials are not committed.

## Decision
No strategy meets the user's profit-in-every-month goal or a durable annual out-of-sample gate; no promotion. Further historical optimization over repeatedly viewed years is not independent validation. Need broker point, contract-size mapping, actual swap/commission/margin, and first genuinely new future calendar periods in immutable shadow/paper evaluation. Native GitHub XAUUSD code remains staged on the research branch; this session was run by the independent bid/ask simulator.