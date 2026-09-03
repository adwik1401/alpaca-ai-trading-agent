# Intraday / 0DTE Strategy Research (2026-09-02)

Triggered by a real problem the user caught: Hybrid VRP+Skew only fires ~11 times/year, which meant a >90% chance of producing **zero trades** in our remaining ~2-day window. Delegated to Antigravity CLI to research what's actually industry-standard for higher-frequency options trading, rather than inventing something under deadline pressure.

## Context: 0DTE is genuinely industry-standard, not a hackathon gimmick

0DTE (zero-days-to-expiration) options on SPY/SPX reportedly make up 45-50%+ of daily S&P 500 options volume. Treated by prop desks/market makers as high-velocity volatility and inventory-rebalancing instruments, not "lottery tickets."

## Four strategies identified

| Strategy | Structure | Bias | Frequency | Hold time | Win rate (claimed) |
|---|---|---|---|---|---|
| **1. 0DTE Iron Condor** (10am entry) | 4-leg credit spread | Neutral | ~1/day (~80% of days) | 2-4 hours | 74-78% |
| 2. Opening Range Breakout (ORB) | 2-leg debit spread | Directional | 1-2/day | 15-60 min | 45-52% |
| 3. VWAP Mean Reversion | 2-leg credit spread | Counter-trend | 2-4/day | 30-75 min | 72-80% |
| 4. VWAP Trend Pullback | 2-leg debit spread | Trend-following | 1-3/day | 20-60 min | 55-60% |

**Caveat**: win rates/Sharpe figures above are Antigravity's secondary claims, not something we've verified against real data — treat as a starting hypothesis, not fact, exactly like we did (and were right to be skeptical about) for the weekly strategy's initial numbers. Must backtest against real Alpaca 1-min/5-min option bars before trusting any of this.

## Strategy 1 in detail (the recommended primary pivot)

- **Entry**: 10:00 AM ET (after the first 30 min settles), only if the market is calm — 30-min opening range < 0.5% of spot AND VWAP slope flat.
- **Strikes**: delta-targeted (~0.10-0.15 delta short strikes) using time-to-close instead of time-to-weekly-expiry in the Black-Scholes T term — same math we already have, different T.
- **Exits**: 50% profit-take, 1.5-2x stop-loss, **mandatory hard close by 3:30 PM ET** (eliminates gamma explosion / pin risk / assignment risk near the close).
- **Why this is the highest-confidence pivot for us specifically**: it's structurally identical to what we already built for the weekly Hybrid strategy (4-leg delta-neutral iron condor, delta-targeted strikes, 50%/stop-loss exits, defined risk) — just re-timed to intraday. Our existing `backtest/black_scholes.py`, `agent/executor.py`, `agent/risk_gates.py`, and the condor-construction logic in `backtest/strategies/common.py` are almost entirely reusable. This massively de-risks building it correctly in the time remaining, versus Strategies 2-4 which need new indicator infrastructure (VWAP bands, ORB detection, RSI) built from scratch.

## Known 0DTE-specific failure modes (must guard against)

| Failure mode | Cause | Defense |
|---|---|---|
| Gamma explosion | Gamma → ∞ as time-to-expiry → 0 | Hard time stop, never hold past 3:30-3:45 PM ET |
| Pin risk / physical assignment | American-style, 0.01 ITM at expiry triggers assignment | Force-liquidate before close, never hold into settlement |
| Slippage / spread blowout | Bid-ask widens sharply in 0DTE during vol spikes | Limit orders at mid, reject if spread >5% of mid (already our rule) |
| Opening whipsaw / false breakouts | First 15-30 min has fake liquidity sweeps | Blackout period 9:30-10:00 AM, require volume confirmation for any breakout signal |
| Leg-in execution risk | Sequential leg execution leaves one side exposed | Atomic MLEG orders only (already our design) |

## Decision (pending user confirmation)

Recommended: pivot the live agent to **Strategy 1 (0DTE Iron Condor)** as the primary approach, reusing existing infrastructure, backtested against real Alpaca intraday option data before going live — not the full "dual/triple-engine" system Antigravity proposed, which is over-scoped for the time remaining. Strategies 2-4 could be considered later if time allows, but are not the priority.
