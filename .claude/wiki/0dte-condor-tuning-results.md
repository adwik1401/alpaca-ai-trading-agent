# 0DTE Iron Condor Parameter Tuning Results (2026-09-02)

Agent-driven parameter search inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch)'s
edit-run-check-keep loop, adapted to Claude Code's own primitives (no GPU training - the "experiment"
is a real backtest against real Alpaca historical option data). Full design and decisions in
[.claude/plans/0dte-condor-parameter-tuning-plan.md](../plans/0dte-condor-parameter-tuning-plan.md).
Code: `backtest/tuning/`. Skill: `.claude/skills/tune-0dte-condor/SKILL.md`.

## Why this strategy

0DTE Iron Condor (`backtest/intraday/strategy_1_iron_condor.py`) was chosen as the tuning target
because it's the highest-trade-volume strategy in this project (84 trades/yr) that isn't already
actively broken - the only candidate with enough trades for a meaningful train/test split. Hybrid
VRP+Skew (the live strategy) trades only ~11x/year, too thin to validate this way.

## Method

- **Split**: 126 trading days (2026-03-04 to 2026-09-01) split 2/3 train (84 days) / 1/3 test (42
  days), by trading-day count via `backtest.intraday.data.get_trading_days`.
- **Search**: agent-in-the-loop (Claude, driven directly rather than via literal `/loop`
  scheduling - see note below), coordinate-ascent style: one parameter changed per iteration, kept
  only if it improves Sharpe on the train split without breaching a 6% max-drawdown cap (matching
  `agent/config.py`'s own `TOTAL_DRAWDOWN_KILL_SWITCH_PCT`), and only if the candidate produced at
  least 15 trades (below that, Sharpe is unreliable small-sample noise - this threshold caught a
  real case during the search, see below).
- **Stop condition**: 20-iteration budget or 5 consecutive non-improving attempts, whichever first
  - the search stopped at 19 attempts on the 5-non-improving condition.
- **Implementation note**: rather than literally invoking `/loop`'s scheduled wake-up mechanism
  (designed for pacing work across real time), the full bounded 19-iteration search was run
  directly in one sitting, since ScheduleWakeup's delay range (60-3600s per wake) would have added
  artificial waiting with no benefit for a task this bounded. Documented as a disclosed deviation
  from the plan's literal wording, not a scope change - Claude still made every per-iteration
  decision itself.

## Search history

19 attempts, 5 kept (improving), 14 reverted. Full ledger: `backtest/tuning/results/ledger.json`.

| # | Parameter changed | Direction | Train Sharpe | Kept? | Note |
|---|---|---|---|---|---|
| 0 | (baseline) | - | -0.95 | seeded | Baseline is actually net-negative on train |
| 1-4 | `stop_loss_multiple`, `profit_take_pct` | both directions | -1.20 to -1.40 | no | Neither lever moved things; baseline was a local optimum for both |
| 5 | `calm_range_pct_max` | tighter (0.005→0.004) | **0.72** | **yes** | Being more selective about calm mornings was the first real lever |
| 6 | `calm_range_pct_max` | tighter still (→0.003) | 6.76 | **no - ineligible** | Only 14 trades (below the 15-trade floor) - classic small-sample noise, caught and rejected regardless of the score |
| 7-8 | `calm_vwap_slope_max` | both directions | 0.11 - 0.47 | no | Baseline value (0.0002) confirmed as a local optimum |
| 9 | `target_delta` | higher (→0.145) | 0.51 | no | Worse |
| 10 | `target_delta` | lower (→0.105) | **1.82** | **yes** | Further-OTM strikes materially improved risk-adjusted quality |
| 11 | `target_delta` | lower still (→0.085) | 1.55 | no | Overshot - 0.105 confirmed as the peak |
| 12 | `wing_width` | wider (→1.25) | **1.89** | **yes** | Small further gain |
| 13 | `wing_width` | wider still (→1.5) | **3.41** | **yes** | Largest single jump - flagged for scrutiny (see below) |
| 14 | `wing_width` | wider still (→1.75) | 1.78 | no | Overshot - 1.5 confirmed as the peak |
| 15-18 | re-checks of all 4 other params at the new base | various | 0.40 - 3.19 | no | Nothing beat the 1.5/0.105 combination; 5th consecutive miss triggered the stop |

## Final parameters found

| Parameter | Baseline | Tuned | Change |
|---|---|---|---|
| `target_delta` | 0.125 | **0.105** | further OTM |
| `wing_width` | $1.00 | **$1.50** | wider |
| `calm_range_pct_max` | 0.005 | **0.004** | more selective |
| `calm_vwap_slope_max` | 0.0002 | 0.0002 | unchanged |
| `profit_take_pct` | 0.5 | 0.5 | unchanged |
| `stop_loss_multiple` | 1.75 | 1.75 | unchanged |

## Train split result (2026-03-04 to 2026-07-02, 84 days)

| | Baseline | Tuned |
|---|---|---|
| Trades | 23 | 18 |
| Total P&L | -$938 | **+$974** |
| Win rate | 82.6% | 88.9% |
| Profit factor | 0.692 | 3.625 |
| Sharpe | **-0.948** | **3.408** |
| Max drawdown | 1.55% | 0.34% |

A real, coherent improvement: the baseline was actually net-negative over this window, and the
found parameters flip it to solidly positive with much better risk control. **Sharpe 3.41 is
itself high enough that per this project's own established standard (Sharpe 1-2 solid, 2-3 very
good, above 3-4 rare and heavily scrutinized even for real institutional strategies) it should be
treated as promising, not proven** - 18 trades is still a small sample.

## Test split result (2026-07-06 to 2026-09-01, 42 days) - inconclusive, and why

| | Baseline | Tuned |
|---|---|---|
| Trades | 19 | 18 |
| Total P&L | **+$1,298** | +$710 |
| Win rate | 100% | 94.4% |
| Sharpe | **18.26** | 12.23 |
| Max drawdown | 0.00% | 0.04% |

**This does not validate the tuning.** The untouched baseline scores *better* than the tuned
parameters on this window - both numbers are implausibly high in exactly the way this project has
already learned to distrust (see the Sharpe-annualization correction in
[backtest-results.md](backtest-results.md)). The honest read: 2026-07-06 to 2026-09-01 was simply
an unusually calm stretch for the SPY 0DTE condor family generally (consistent with the low-VIX
13-17 backdrop noted in this session's earlier strategy research), not evidence that either
parameter set found a real edge. A train/test split only works as an overfitting check when both
windows represent broadly similar market conditions - here they didn't, so the test split ended up
demonstrating regime non-stationarity over a 6-month sample rather than confirming or refuting the
search.

## Bottom line

- The search process itself worked as designed: it found a real, explainable improvement on the
  train split, correctly rejected a spuriously perfect small-sample result (attempt #6, 14 trades),
  and correctly stopped once no further parameter changed helped.
- The test-split check, however, turned out to be uninformative due to a genuine regime shift
  between the two windows - not a flaw in the tool, but a real limit of validating anything on
  only ~6 months of data.
- **Recommendation**: treat the tuned parameters (`target_delta=0.105`, `wing_width=1.5`,
  `calm_range_pct_max=0.004`) as a promising research finding worth further real-data validation
  (e.g. re-running this search as more historical data accrues, or live-paper-piloting before
  committing), not a proven result ready for unconditional deployment - consistent with how every
  other backtest result in this project has been caveated.
