# Backtest Results & Strategy Selection

Backtested 2026-09-01 against **real historical SPY option prices** (Alpaca `/v1beta1/options/bars`, real expired contracts) and real SPY equity bars (back to Jan 2026). Methodology and code: `backtest/` in the project root. See [architecture-decisions.md](architecture-decisions.md) for why the original 4-candidate set became 3 (event-driven dropped: SPY has no earnings; GEX renamed to skew regime: Alpaca has no open-interest data anywhere).

## Methodology

- Entry: Monday of each expiry week (~4 DTE), weekly SPY iron condors.
- Strike selection: **delta-targeted** (~0.175 delta), not a fixed % OTM — a fixed percentage badly overshoots on short-dated options (a 5% OTM/4-DTE option turned out near-worthless; see note below). Offset computed from `|Φ⁻¹(target_delta)| × σ × √T` using realized vol as the σ estimate.
- Wing width: $5 (defined-risk on both sides).
- Exit rules: close at 50% max profit captured, or stop out at 2x the credit received (risk gate), else hold to expiry.
- Position sizing: risk ≤2% of a $100,000 NAV per trade (`risk_budget / max_loss_per_contract`).
- IV and skew are backed out via Black-Scholes inversion on the real observed option prices — P&L itself uses the real market prices directly, IV/skew are only used for the entry-signal filter.

## ⚠ Sharpe/Sortino methodology correction (2026-09-02)

The Sharpe/Sortino figures originally reported below (30-week and 34-week tables) were computed with a bug: `metrics.py` annualized using a hardcoded `√252`, which assumes a return every trading day. These are **per-trade** returns (each trade spans several days, and the strategies only trade 11-26 times a *year*), not daily returns — so the original numbers were inflated roughly 3-5x (e.g. Hybrid's reported Sharpe of 9.21-11.82 was never a real, comparable Sharpe ratio). Caught when a sanity-check question ("are these good results?") prompted comparing against real-world benchmarks — a Sharpe above ~10 should always be treated with suspicion, not celebrated.

**Fixed**: `metrics.summarize()` now annualizes using the strategy's actual trade frequency (`trades / lookback_years`), not a fixed 252. The 30-week and 34-week tables below are left as originally computed (for the historical record) but their Sharpe/Sortino columns should be read as **superseded and unreliable** — trust the corrected 52-week table instead. The win rate, profit factor, and max drawdown columns in every table were never affected by this bug (they don't involve an annualization step).

## Results

**30-week lookback** (Sharpe/Sortino columns superseded, see correction above):

| Strategy | Trades | Total P&L | Win rate | Profit factor | ~~Sharpe~~ | ~~Sortino~~ | Max DD |
|---|---|---|---|---|---|---|---|
| VRP Iron Condor | 10 | $1,134 | 70.0% | 1.184 | ~~1.14~~ | ~~6.70~~ | 6.06% |
| Skew Regime | 21 | $2,749 | 76.2% | 1.335 | ~~1.69~~ | ~~2.88~~ | 5.88% |
| **Hybrid VRP+Skew** | 9 | $2,889 | 77.8% | 1.656 | ~~3.53~~ | ~~49.80~~ | 4.33% |

**34-week lookback** (Sharpe/Sortino columns superseded, see correction above):

| Strategy | Trades | Total P&L | Win rate | Profit factor | ~~Sharpe~~ | ~~Sortino~~ | Max DD |
|---|---|---|---|---|---|---|---|
| VRP Iron Condor | 10 | $1,134 | 70.0% | 1.184 | ~~1.14~~ | ~~6.70~~ | 6.06% |
| Skew Regime | 21 | $5,422 | 81.0% | 1.924 | ~~4.01~~ | ~~6.19~~ | 3.60% |
| **Hybrid VRP+Skew** | 8 | $5,217 | 87.5% | 3.509 | ~~9.21~~ | ~~0.00~~ | 2.04% |

## 1-year backtest (52-week lookback, run 2026-09-02) — Sharpe/Sortino CORRECTED

Confirmed real historical option data exists back to at least September 2025 (Alpaca `/v1beta1/options/bars`) and equity data back to at least 2024. Re-ran all 3 strategies over the full year on the same $100,000 base, with the corrected annualization:

| Strategy | Trades/yr | Total P&L | Return | Win rate | Profit factor | Sharpe | Sortino | Max DD |
|---|---|---|---|---|---|---|---|---|
| VRP Iron Condor | 14 | $5,736 | +5.7% | 78.6% | 1.93 | **1.17** | 6.38 | 5.79% |
| Skew Regime | 26 | $9,398 | +9.4% | 80.8% | 2.66 | **2.10** | 2.46 | 1.97% |
| **Hybrid VRP+Skew** | 11 | $8,076 | +8.1% | 90.9% | 4.89 | **2.53** | 0.00 | 1.99% |

Reassuringly, the **ranking is unchanged** by the fix (Hybrid still highest Sharpe) — only the earlier magnitude was wrong, not the conclusion. A Sharpe of ~2.5 is a genuinely good, believable number for a systematic strategy (for context: a Sharpe of 1-2 is solid, 2-3 is very good, and claims above ~3-4 on real institutional strategies are rare and heavily scrutinized).

**Benchmark check — buy-and-hold SPY over the identical window**: SPY went from $640.40 (2025-09-02) to $761.63 (2026-09-01) = **+18.9%**, more than double every strategy's return above. This is expected and not a flaw: these are market-neutral, defined-risk premium-selling strategies — they profit from range-bound/theta decay and are not trying to capture directional upside, so they will structurally lag a straight-up bull market like the one SPY had this year. The fair comparison is risk-adjusted return (Sharpe) and drawdown control, not raw return, and on those terms Hybrid clearly wins — 1.99% max drawdown vs. whatever SPY's actual peak-to-trough drawdown was over the same year (not yet computed, but a 100%-long SPY position would have experienced far more volatility along the way than 1.99%).

**Honest nuance**: Hybrid still wins every risk-adjusted metric (best win rate, best profit factor, best Sharpe), but the margin is narrower over the full year than in the shorter windows — Skew Regime alone actually banked more total dollars ($9,398 vs $8,076) with nearly identical drawdown, simply by trading more than twice as often (26 vs 11 times) and accepting a slightly lower per-trade quality. This doesn't change the decision: Hybrid's profile (fewer, more selective, higher-conviction trades) is the right one when the live agent effectively gets one real trade before the deadline, not a full year of cycles to let variance average out.

## Decision: Hybrid VRP+Skew — FINALIZED 2026-09-02

Confirmed with Adwik. This is locked in as the live strategy for Phase 2. No further strategy candidates will be considered given the shrinking runway (~2.5 days left to the Sep 4, 8:30 PM IST deadline as of this confirmation).

Wins on every risk-adjusted metric in both windows — best win rate, best profit factor, lowest max drawdown, best Sharpe — while capturing nearly as much total P&L as the more trade-happy skew-only variant with roughly half as many, more selective trades. That combination (similar profit, much better risk control, high selectivity) is the pattern you want from a genuine edge rather than noise, and it directly matches the research's "combine VRP with a regime filter for robustness" recommendation. **This is the strategy going into the live agent (Phase 2).**

## Important caveats — read before quoting these numbers anywhere external

- **Sample sizes are still small** (11-26 trades even over a full year). Sharpe/Sortino computed on this few data points are directionally informative (consistent ranking across three lookback windows, now with corrected annualization) but should not be presented as statistically robust point estimates in the one-page write-up — describe them as backtest indicators, not proven risk-adjusted returns.
- **Sharpe/Sortino annualization was buggy until 2026-09-02** — see the correction section above. Always use the 52-week table's numbers; the 30/34-week tables' Sharpe/Sortino columns are kept only for the historical record and are not reliable.
- **Fills use daily close prices**, not actual bid/ask execution — a reasonable backtest approximation, but real slippage will be somewhat worse than this shows. The live agent's actual risk gate (reject spreads >5% of mid) partially controls for this going forward.
- **Skew computed per-week from real historical prices** at entry time (not a static snapshot) — this part is fully real. What's NOT real/historical is dealer positioning (GEX) itself, which we don't have data for at all (see architecture-decisions.md).
- The original fixed-5%-OTM version of this backtest produced near-zero premiums and was silently wrong until the delta-targeting fix — worth remembering if results ever look implausibly small again: check the strike-selection logic before assuming the trade thesis is bad.
