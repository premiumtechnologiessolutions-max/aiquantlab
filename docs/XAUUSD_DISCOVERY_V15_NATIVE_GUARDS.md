# XAUUSD V15: Candle auction search and native research guardrails (2026-10-24)

Status: **research-only / rejected / not merged to main**.

## Native code in this branch
- `src/ai_quant_lab/config.py` admits `XAUUSD` to the validated instrument set for research.
- `src/ai_quant_lab/backtesting/engine.py` prohibits gold backtests without an **explicit, non-null broker point_size** and explicit **quantity measured in troy ounces**. Existing FX defaults remain unchanged.
- `src/ai_quant_lab/simulation.py` prohibits XAUUSD paper/shadow quotes without an explicitly supplied price point size.
- `src/ai_quant_lab/broker/mt5_demo.py` **blocks manual XAUUSD demo orders** pending broker-specific lot/contract sizing, margin and stop validation, despite XAUUSD being accepted for historical data/research.
- `tests/test_xauusd_support.py` tests gold model validation, no fallback FX sizing, per-ounce spread/slippage/fee, forex compatibility, paper-point guard and demo-order rejection.
- `.github/workflows/xauusd-research-check.yml` configures read-only, branch-limited CI using Python 3.12; at this report **a completed run could not be verified**, so tests are NOT claimed passed on GitHub CI.

## 96 additional, preregistered standalone historical experiments
Data: user's 17 yearly gold bid/ask JSON archives aggregated to 397,299 M15 candles (2010-Jan to 2026-Sep20). The cached `ts` is **M1 component count**, usually 15, **not true market tick volume**. No order-flow claims are supported.

Four new price action families, 24 parameterizations each: completed candle impulse follow/fade, failed auction channel wick, volatility-compression / inside breakout. Development 2010–2017, confirmation 2018–2021, 2022–Sep2026 already-seen diagnostics. Signal on completed M15, fill on next M15 executable bid/ask open, one trade at a time, 30min entry-gap limit, $5 max spread cap, $0.10/oz slippage each side, $0.05/oz nominal roundtrip fee. No broker swap or account capital allocation.

Of 96 trials, **one** met initial development gates: short-only inside breakout: volatility ratio <0.65, candle body/range >=0.75, initial stop 5 ATR64, trailing stop 4 ATR64, hold <=288 M15 bars. Performance:

| Window | Trade count | Net R | Winning months | Winning years |
|---|---:|---:|---:|---:|
| 2010–2017 development | 184 | +0.22 | 33/96 | 4/8 |
| 2018–2021 confirmation | 105 | **−16.12** | 12/48 | 0/4 |
| 2022–Sep 2026 seen diagnostics | 80 | **−5.10** | 16/57 | 1/5 |

Tripled modelled slippage and fees: −8.31 R in seen diagnostics. **Reject candidate and do not rerank on later years.**

Standalone research code and exact M15 cache were packaged as `no_risk_fx_discovery_session5_2026_10_24.zip` in project conversation. Reproducible execution after re-extraction yielded **6/6 tests passed** and same results (distinct from native GitHub CI). Archive contains source, 96-row ledger, selection table, annual/monthly results, SHA256 manifest and run logs. No source prices/ZIP or broker credentials were pushed to GitHub.

## Next blockers
Native CLI and MarketBar currently model mid-OHLC plus spread points, not exact bid/ask extrema; native backtest must NOT be assumed equivalent to standalone bid/ask stop simulator. Before approving a gold strategy, define the broker's gold price increment, contract size, lot mapping, commission, swaps, calendar and rollover, and construct a genuinely prospective validation sample. Profit every month cannot be guaranteed.

Decision: **0 confirmed new strategies**; gold native integration is staged and guarded but remains unmerged/unverified by CI.
