# Return-Competitive Candidate Strategy Backtest Results (2026-09-02)

Triggered by a legitimate concern: Hybrid VRP+Skew's 52-week backtest returned +8.1% vs. SPY
buy-and-hold's +18.9% over the same window (see [backtest-results.md](backtest-results.md)) - is
there a real, industry-standard options strategy that's actually return-competitive with the index,
not just risk-adjusted-good? Delegated research to Antigravity CLI, which returned 4 ranked
candidates: PMCC/call diagonal (top pick, bull-case 22-31% CAGR), bull risk reversal, 90/10 barbell,
and momentum-timed verticals. Full research write-up logged in the conversation; this page covers
the real-data backtest verification that followed. Code: `backtest/candidates/`.

## Two hard data constraints discovered before any results could be trusted

1. **No OPRA agreement on this account** - Alpaca's historical option-bars endpoint 403s
   ("OPRA agreement is not signed") for ANY contract that hasn't reached its own expiration date
   yet, even for days already in the past. Confirmed by direct API testing: a contract expiring
   tomorrow 403s for its entire history; one that expired last week returns 200 with real bars.
2. **~14-day print-coverage floor** - even for already-expired contracts, this account's SPY
   options data has essentially no trade prints earlier than ~14 calendar days before a contract's
   own expiry, regardless of moneyness. Confirmed across multiple expiries/strikes: a deep-ITM
   45-DTE-out strike returned zero prints ever; near-ATM and OTM strikes consistently showed their
   first print at exactly 14 DTE. Deep ITM was *worse* than ATM/OTM, not better as initially
   assumed (ITM options don't have continuous stock-replacement-driven flow on this feed).

Both are real infrastructure limits of this account's data tier, not bugs - discovered the same way
every other real constraint in this project was (missing open-interest, no SPY earnings): by hitting
it directly and verifying with raw API calls before trusting any downstream number.

## Consequence: all 4 candidates had to be redesigned to fit inside the data that actually exists

The research proposed 30-90 DTE entries throughout. All 4 were compressed to ~12 DTE entries (a
2-day safety margin inside the 14-day floor) rather than silently backtesting on data that doesn't
exist. This was disclosed to the user as a real tradeoff before proceeding (chose: redesign and
backtest the compressed version over reverting immediately). Full detail and reasoning in each
strategy module's docstring under `backtest/candidates/`.

**Important honest finding**: for PMCC specifically, compression didn't just shorten the strategy -
it broke its core thesis. A 12-DTE 0.80-delta "deep ITM" call has nowhere near the dollar cushion a
60-90-DTE 0.80-delta call would have (confirmed directly: one long leg round-tripped from real ITM
value to $0.01 after a normal ~1.9% SPY pullback over its 12-day life - not a data bug, verified
against real SPY closes and option bars). The "leveraged stock-replacement with structural downside
truncation" idea Antigravity's research was built on requires long-dated options; it doesn't survive
compression to a timeframe this account's data can actually support.

## Results (26-week / 6-month backtest, real SPY option and equity data)

| Strategy | Trades | Total P&L | Return | Win rate | Profit factor | Sharpe | Sortino | Max DD |
|---|---|---|---|---|---|---|---|---|
| Barbell call spread | 21 | -$6,540 | -6.54% | 38.1% | 0.707 | -0.97 | -2.80 | 7.95% |
| Momentum vertical | 21 | $36 | +0.04% | 42.9% | 1.002 | 0.06 | 0.20 | 9.09% |
| **Risk reversal** | 8 | $4,120 | **+4.12%** | 75.0% | 2.184 | **1.59** | 3.22 | **3.23%** |
| PMCC diagonal | 42 rolls | -$63,231 | **-63.23%** | n/a | n/a | -0.11 | -0.13 | **86.17%** |

**Benchmark - SPY buy-and-hold, same window (2026-03-04 to 2026-09-01)**: **+11.17%**, max drawdown
7.75%.

PMCC's Sharpe/Sortino are computed on weekly marks (periods_per_year=52), not the same "kind" of
Sharpe as the other 3 candidates' per-trade-frequency numbers - see `pmcc_diagonal.py`'s module
docstring. Not directly comparable to each other without that context, though the -63% return and
86% drawdown need no such caveat to interpret.

## Decision: none of the 4 candidates replace Hybrid VRP+Skew

- **PMCC** (the research's #1-ranked "top pick", projected 22-31% bull-case CAGR) was the worst
  performer by a wide margin once tested for real: -63% return, 86% max drawdown. A concrete,
  data-backed illustration of why theoretical/illustrative math from research should never be
  trusted over a real backtest before shipping - exactly the caution flagged to the user before
  this work began.
- **Barbell and momentum verticals** both underperformed or roughly matched flat/cash over the
  window - no real edge found.
- **Risk reversal** was the only genuinely respectable candidate (Sharpe 1.59, Sortino 3.22, max DD
  3.23%, 75% win rate) - but still underperforms both SPY's raw +11.17% return over the same window
  AND the already-live Hybrid strategy's real, previously-verified 52-week numbers (Sharpe 2.53, max
  DD 1.99% - see [backtest-results.md](backtest-results.md)). Worth remembering as a candidate for
  future iteration beyond this hackathon, not as a replacement under the current deadline.

**This is now the 4th consecutive research/backtest cycle in one day (2026-09-02) that failed to
find a real-data-verified improvement over Hybrid VRP+Skew** (see also
[intraday-backtest-results.md](intraday-backtest-results.md)'s 3 prior reaffirmations). Hybrid
VRP+Skew remains the live strategy for Phase 2 - no code changes to the live agent from this
exploration.
