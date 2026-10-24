# XAUUSD Research — Discovery 13/14 (2026-10-24)

**Research only — no trading approval, no proven all-month profitable system.**

Data: user's `Gold data.zip` (17 annual JSON files, 2010-01-01–2026-09-20), aggregated to 397,299 XAUUSD M15 bars with separate bid/ask OHLC. Original ZIP SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Derived M15 SHA256: `4e1e39e433718da0bd92f48b0f36fc1c55339ca98b699735d8379a57a8640d71`.

Fixed chronology: 2010–2017 development; 2018–2021 confirmation; 2022–Sep 2026 **already inspected historical diagnostics, not an untouched holdout**. Next completed M15 bid/ask open fills, $0.10/oz slippage per side, $0.05/oz roundtrip fee, $5/oz entry spread cap, <=30-minute signal gaps, pessimistic stop fills; illustrative and not broker-calibrated. R is trade-normalized risk return, not a dollar account balance or portfolio return. No contract-size, actual swap, margin, commissions or live broker executions.

## Discovery 13 — 396 structural trials

Eight families: prior completed monthly or quarterly high/low breakouts and rejection/retests, and causally confirmed pivot breakouts/sweeps/retests. Confirmation lags 4/12 M15 bars, ATR thresholds, direction and volatility/trend filters, ATR trailing exit schedules.

15/396 development-eligible parameter rows (at least 30 trades, positive development R, >=4 positive development years); **0/8** development-selected family representatives passed confirmation (net R >0, >=25/48 positive months, >=3/4 years, >=20 trades).

- Monthly retest: development +2.98R, 15/96 positive months; confirmation −0.84R, 8/48 months.
- Quarterly breakout: development +5.52R, 11/96 months; confirmation −1.16R, 4/48.
- Pivot retest: development +26.85R, 40/96 months; confirmation −9.12R, 21/48; inspected 2022+ diagnostic −17.57R.

## Discovery 14 — 576 persistent Fibonacci trials

Confirmed pivot waves; max 16 active waves, retracements at .382/.500/.618/.786; wave invalidation after 2 consecutive closes through origin or age threshold; tested reclaim, wick rejection, and against-wave structural breakdown; varied pivot lag, minimum wave amplitude, confluence, direction, ATR stop/trailing configuration.

**0/576** met development eligibility (>=60 trades, positive net R, >=5/8 years). Best *absolute* development R across the 576 was approximately −0.15R. An unqualified illustrative rule had 52/96 winning dev months but −32.16R total dev R, −46.26R confirmation, −15.20R inspected 2022+ diagnostics (−40.63R under 3x added slip/fee). It is NOT a viable selection.

## Verification and engineering blocker

Seven new deterministic unit tests all passed: monthly lag, confirmation timing, prefix-invariant levels and signals (including persistent wave), synthetic wave confirmation, bid/ask next-bar entry. A cross-dataset cache keyed without dataset identity was found, corrected, and Discovery 13 rerun without changed research conclusions.

**972 newly evaluated parameter rows; no promotion.** A full executable research ZIP with M15 quote cache, source Python, all trials, monthly/yearly tables, SHA256 and test logs was delivered in the project conversation (Session 4). This branch records research; it still does not integrate gold into `aiquantlab`'s native FX-only core. Do not merely add XAUUSD to `ForexPair`: the engine's default forex point size is 0.00001 for non-JPY, which would silently misrepresent gold transaction costs. Native integration requires explicit broker instrument specifications and gold-specific margin/swap economics, then truly prospective shadow data.

No strategy can guarantee a profitable result every calendar month.
