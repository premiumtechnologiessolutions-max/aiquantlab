# XAUUSD Discovery 16–19: session auctions and monthly mark-to-market (2026-10-24)

**Research only — no live or demo orders, no candidate approved.** Source dataset is user's 17-year XAUUSD bid/ask archive, 397,299 M15 candles (Jan 2010–Sep 20, 2026). Derived M15 cache is in user-delivered ZIP but has **not** been committed to GitHub. Baseline costs are actual bid/ask quote spread plus hypothetical $0.10/oz entry and exit slippage and $0.05/oz roundtrip fee, without broker swap, margin, financing or contract/lot conversion. Schedules below are fixed UTC proxy sessions, not broker-calibrated DST calendars.

**Discovery16 — 270 predeclared trial configurations:** completed-Asia (00–06 UTC), London (07–09) and US (13–14) reference ranges; breakout or sweep/rejection after the reference window. Grid = five families × three ATR margins × three direction options × two prior volatility gates × three stop/trail/hold profiles. Development 2010–17 only for candidate selection, confirmation 2018–21; 2022–Sep2026 was **already inspected in earlier sessions**, so is NOT a pristine blind holdout. Only **one** trial passed development criteria, **none** passed confirmation.

- Dev-picked US-range sweep: long after a 0.5-ATR low sweep, entry signal after 14:00 UTC, stop = 5x ATR64, trailing = 4x ATR64, max 288 M15 bars.
- 2010–17: +5.05 trade-risk units R; 44/96 positive exit-attributed months; 4/8 years.
- 2018–21: **−26.22R**, 20/48 positive months, **0/4 positive years**. **REJECT.**
- Previously inspected 2022–Sep2026: +27.11R, 27/57 exit-attributed months, 4/5 years. **Do not promote based on this; confirmation failed.**

**Discovery17 — corrected monthly P&L recognition:** Built independent per-bar bid/ask mark-to-liquidation accounting of open positions (reconciled exactly to locked closed-trade ledger). Prior exit-month-only reporting can misclassify a month when positions cross month-end. Recent 2022–Sep2026 fixed-one-ounce baseline-cost results:

| Locked model | Profitable months — exit R | Profitable months — month-end R | Profitable months — month-end USD/oz | Net USD/oz |
|---|---:|---:|---:|---:|
| V4 extreme-move continuation | 23/57 | **24/57** | 23/57 | +$17.00 |
| V11 completed weekly range breakout | 29/57 | 29/57 | **28/57** | +$249.65 |
| V16 rejected US-range sweep | 27/57 | 27/57 | **28/57** | +$1,000.57 |

**R** is return per trade divided by its own ATR stop size, summed over trades; NOT cash equity return. With fixed one-oz trades, monetary win-month signs can differ. No broker holding financing, margin or actual lot sizing included.

**Discovery18 — baseline/uncertainty:** One ounce continuously held had **34/57** recent positive months and +$2,543.25/oz price movement (no financing), but has radically different exposure/risk. Descriptive 20,000 circular 3-month block bootstraps on inspected monthly USD/oz gave broad approximate total ranges: V4 [−$643, +$689], V11 [−$382, +$942], V16 [+$20, +$2,401]. The V16 interval is not independent validation: recent era was seen, plus 2018–21 failure.

**Discovery19 — increased slippage/fee costs:** With bid/ask spread included in every run, recent USD/oz MTM at 1x / 3x / 5x *additional* execution costs:
- V4: +$17 / −$97 / −$211.
- V11 weekly: +$250 / +$79 / **−$92**.
- V16 US sweep: +$1,001 / +$802 / +$604 (**still rejected because confirmation was 0/4 positive years; at 5x its summed risk-normalized R was negative**).

**Reproducibility:** Five synthetic regression tests passed (complete-window timing, incomplete-session rejection, first signal per direction/day, open-trade month-end MTM, future-bar invariance). The independent Session 6 ZIP, furnished in the conversation, contains standalone Python, the user's derived gold M15 cache, exact 270 trial ledger, monthly/annual output, a SHA256 manifest, and replay logs. Extracting in a new directory and running all tests / four workflows produced **8/8 byte-identical output CSV/JSON hashes**.

**Next steps:** Broker gold lot-to-ounce/point/swap/margin validation; one-position account-level cash sizing and margin risk; immutable prospective strategy registry on *new incoming months*. Do not optimize on the repeatedly inspected historical diagnostic period. This branch's native XAUUSD support remains staged and CI completion unverified. **No method proves profitability in every month.**