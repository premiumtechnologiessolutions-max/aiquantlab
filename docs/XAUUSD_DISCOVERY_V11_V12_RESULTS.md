# XAUUSD Discovery V11–V12 (2026-10-24)

**Research only. No live-trading approval and no proven all-month profitable strategy.**

User archive: 17 annual XAUUSD bid/ask files, 397,299 aggregated M15 bars from 2010-01-01 to 2026-09-20 (2026 incomplete). Next-bar bid/ask executable fills, $0.10/oz slip each side, $0.05/oz roundtrip additional fee, $5/oz entry spread cap, no stale signals >30 minutes; ATR trailing stops. Trading costs are not broker-calibrated; swap/margin are not included in baseline.

**Partition discipline:** choose strategy using 2010–2017 development only, 2018–2021 temporal confirmation; 2022–2026 diagnostics **already seen in past sessions** (NOT blind OOS).

## Discovery 11
216 strategies across 4 hypothesis families: prior completed weekly high/low breakout, weekly price sweep/rejection, weekly retest, and 24-M15 return-volatility squeeze breakout. One representative per family locked solely on development. **Zero of four** passed the predeclared confirmation gate (profit >0, 25/48 positive months, 3/4 positive years, 40+ trades).

- Weekly breakout representative: LONG only; M15 close crosses above prior Mon–Sun week high, initial SL = 5× ATR64, trailing stop = 4× ATR64, max 288 M15 bars.
- 2010–17: +11.33 R; 46/96 months.
- 2018–21: +3.10 R; 21/48 months (**confirmation fails stability**).
- 2022–Sep26 historic diagnostic: 343 trades, +24.68 R; 29/57 months; 3/5 years, max drawdown 14.04 R, PF 1.264; 2022 −11.10 R, partial 2026 −1.99 R.
- Cost stress: at 3× slip/fee +12.78 R; at 5× slip/fee +0.87 R. Hypothetical $0.25/oz/calendar 24h carry: +21.63 R vs +24.68 R (not a real swap quote).
- 120 past-signal time-shift placebo runs put realized net R at ~95th percentile of those controls; **not a calibrated significance test**. 10,000 three-month circular monthly-block historical bootstrap runs gave approximate net-R 95% interval **−5.03 to +54.63**, including loss.

Across all 216 trials, 8 parameter rows satisfy the confirmation gate considered by itself, but every one had negative 2010–2017 development R (−16.96R or worse), with duplicate-like variants; zero passed development-positive AND confirmation gates. Selecting these rows now would be confirmation-data snooping.\n\nOther family representatives lost on validation: weekly sweep −6.96 R; weekly retest −16.40 R; squeeze breakout −37.81 R (2018–21).

## Discovery 12
Reimplemented a **single-position netting research simulator** for two locked models (V4 z-score continuation and new weekly breakout). One open position total; cancel simultaneous opposite intents; entering on following M15 open; individual exit timelines retained. V4-only and weekly-only trade ledgers replay exactly the earlier independent simulator (numeric equality tests).

| Model | 2018–21 R | Profitable months | 2022–Sep26 R | Profitable months | Recent DD |
|---|---:|---:|---:|---:|---:|
| V4 alone | +26.22 | 30/48 | +4.13 | 23/57 | 11.87 R |
| Weekly alone | +3.10 | 21/48 | +24.68 | 29/57 | 14.04 R |
| No-opposite union | +29.08 | 30/48 | +28.14 | 29/57 | 19.83 R |
| Strict agreement | +4.86 | 7/48 | +3.27 | 5/57 | 0.67 R |

Union: 514 diagnostic trades; costs at 3× +10.84 R; 5× **−6.47 R**. Thus no gain in positive-month count, worse drawdown and fee vulnerability. Consensus mostly does not trade; zero months count as non-positive.

Five new synthetic regression tests passed (prior-week values, prefix invariance, conflict suppression, next-open entry, consensus requiring both strategies), plus standalone simulator trade-array replay checks.

**Decision:** reject promotion. The next implementation prerequisite is proper XAUUSD support in the main lab's seven-pair FX-only schema, broker contract size/tick economics, swap and margin, fixed trading-day rollover, and genuinely prospective out-of-sample shadow data. This branch currently stores research reports; core XAUUSD integration is **not yet complete**.

Reproducible runnable Python scripts, 216-trial ledger, monthly/yearly series, 120 placebos, trade ledgers, test output and full source package were generated and supplied in the project conversation as `no_risk_fx_discovery_session3_2026_10_24.zip`. Neither price ZIP nor private broker credentials are committed.
