# Intraday Strategy Backtest Results (2026-09-02)

Backtested all 4 candidate intraday/0DTE strategies from [intraday-strategy-research.md](intraday-strategy-research.md) against real historical SPY option data (5-min bars), triggered by the concern that weekly Hybrid VRP+Skew only fires ~11x/year and might produce zero trades in our remaining live window. Code: `backtest/intraday/`.

## Two real bugs caught before trusting any results

1. **Strategy 3 sign bug**: reused `common.price_vertical_at` (designed for debit spreads, `long − short` where "long" = the near/expensive leg) inside a credit-spread structure where "short" meant the near/sold leg — the opposite convention. This flipped the sign and made every trade falsely register as "profit-take" within 5 minutes on pure noise (initial 5-day sample showed 100% win rate, +5.56% in 5 days — implausible on its face). Fixed with unambiguous `sold`/`bought` leg naming and a dedicated pricer.
2. Strategy 1 and 4 checked out clean on manual inspection (realistic hold times, P&L matching the stated exit thresholds).

Caught by the same discipline applied throughout this project: never trust a suspiciously good (or suspiciously bad) result without inspecting the actual trade records.

## 6-month results (126 trading days, 2026-03-04 to 2026-09-01)

| Strategy | Trades/yr | 6-mo P&L | Return | Win rate | Profit factor | Sharpe | Sortino | Max DD |
|---|---|---|---|---|---|---|---|---|
| 0DTE Iron Condor | 84 | $360 | +0.36% | 90.5% | 1.118 | 0.305 | 0.369 | 1.55% |
| ORB Breakout | 230 | −$701 | −0.70% | 41.7% | 0.989 | 0.011 | 0.056 | 7.86% |
| VWAP Mean Reversion | 378 | −$3,571 | −3.57% | 65.1% | 0.914 | −0.607 | −0.740 | 13.61% |
| VWAP Trend Pullback | 110 | −$3,332 | −3.33% | 41.8% | 0.864 | −0.690 | −3.421 | 6.92% |

**Compare to weekly Hybrid VRP+Skew** (52-week backtest, see backtest-results.md): 11 trades/yr, +8.1% return, 90.9% win rate, 4.89 profit factor, **Sharpe 2.53**, 1.99% max drawdown. Every intraday candidate loses decisively on risk-adjusted terms.

## Interpretation

- **3 of 4 intraday strategies lose money over 6 months.** The only marginally-profitable one (0DTE Iron Condor, Sharpe 0.30) is a naive, lightly-filtered version of the same condor mechanics as Hybrid — its weak edge relative to Hybrid's strong one is direct evidence that the *selectivity* (only trading when signals are genuinely favorable) is what generates edge, not the underlying structure.
- **VWAP Mean Reversion is the cautionary tale**: looked excellent in a 5-day sample (100% win rate) but produces the worst 6-month drawdown of all five strategies tested in this project (13.61%) — the textbook mean-reversion failure mode of many small wins erased by rare large losses when a real trend emerges. A short sample would have badly misled us here.
- **Direct answer to "will Hybrid even get a trade in 2 days?"**: the live agent's own pipeline tests today (2026-09-02) already returned `vrp_ok=True, skew_ok=True` for both the Sep 3 and Sep 4 targets — real, live, favorable conditions, observed directly, not a hopeful extrapolation from the ~11/year base rate. The base rate describes an average across all market conditions; today's actual conditions already independently qualify.

## Strategy 5: weekly Hybrid VRP+Skew logic, transplanted to 0DTE

Follow-up test: instead of a new signal, apply the SAME validated filter (IV exceeds RV by a threshold, skew not elevated) but checked daily at 10 AM against the 0DTE chain. First attempt found a real regime-mismatch bug: comparing 0DTE IV (a ~5.5-hour-horizon measure) against daily-close RV20 (a 20-*day* measure) produced IV consistently BELOW RV (e.g. 6.6% vs 13.2%) — the opposite of what the filter needs, in 10/10 test days. Not a calculation bug; a genuine "wrong yardstick" problem.

**Fix**: replaced RV20 with a realized-vol estimate computed on the same high-frequency (5-min) basis, pooled over the trailing 15 trading days (built from bars already fetched during the backtest walk-forward — no extra API calls, no look-ahead). Also recalibrated the VRP threshold from an absolute point-spread (weekly's `+0.02`, calibrated for ~10-20% vol) to a relative ratio (`IV/RV >= 1.10`), since intraday vol runs much lower (~6-8%) and an absolute threshold from a different vol regime doesn't transfer.

**6-month result after the fix**: 18 trades/126 days (36/yr) — **win rate 27.8%, profit factor 0.646, Sharpe −1.224, −$1,598 (6mo)**. The worst-performing strategy tested in this entire exploration, including the 4 original intraday candidates.

**Why it still fails even after the fix is correct**: on a 4-7 day horizon, "IV exceeds RV" plausibly means options are irrationally overpriced relative to typical volatility — a real edge worth harvesting. On a same-day horizon, "IV exceeds RV" more likely means the market has correctly priced in a real, materializing risk for *today specifically* — the opposite interpretation. Shortening the timescale doesn't just change the numbers, it can flip what the signal actually means.

## Decision: stay with weekly Hybrid VRP+Skew — reaffirmed 2026-09-02 (twice)

More trades is not the same thing as a better strategy. Six distinct configurations were tested across two timescales (4 industry-standard intraday strategies, plus the weekly Hybrid logic transplanted to 0DTE both naively and after a genuine bug fix) and none beat weekly Hybrid on any risk-adjusted measure — most actively lose money over 6 months. Combined with the fact that Hybrid's entry conditions are already live-favorable today, there is no evidence-based reason to switch. This work was not wasted: it converted a real, valid worry ("what if we never get a trade?") into a thoroughly tested question, caught 3 real implementation bugs along the way (a strike-selection bug, a Sharpe-annualization bug, a credit-spread sign bug), and the answer came back clearly: the original strategy's rarity is a feature of genuine selectivity, not a flaw to engineer away.
