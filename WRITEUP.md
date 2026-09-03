# Options Alpha Agent — Write-up

**Live account:** `PA3WNF5ZV8W3` (Alpaca paper, $100,000 starting balance, options level 3)
**Repo:** [github.com/adwik1401/alpaca-ai-trading-agent](https://github.com/adwik1401/alpaca-ai-trading-agent)

## Strategy: Hybrid VRP + Skew Iron Condor

A market-neutral, defined-risk options strategy: sell weekly SPY iron condors when two independent
signals agree the setup is favorable.

- **Volatility risk premium (VRP)**: enter only when implied volatility (backed out via
  Black-Scholes from real observed option prices) exceeds 20-day realized volatility by ≥2 vol
  points — i.e. options are priced richer than actual recent movement justifies.
- **Skew regime filter**: enter only when put-call IV skew isn't elevated relative to its own
  recent history — avoids selling premium into a market that's already pricing in unusual
  hedging demand/fear.
- **Strikes**: delta-targeted (~0.175), not a fixed % OTM — short-dated options need this to avoid
  selecting near-worthless strikes. **Wings**: $5 wide, defined risk on both sides. **Exit**: 50%
  max-profit take, or a 2x-credit stop-loss, else hold to expiry.

**Why this strategy, not a directional one**: 4 return-competitive alternatives (a leveraged call
diagonal, a bull risk reversal, a call-spread barbell, momentum verticals) were researched and
backtested against real historical data specifically to check whether something could beat SPY's
raw return. None did on a risk-adjusted basis, and the top-ranked candidate (a leveraged diagonal)
was the worst performer once tested for real — a normal few-percent pullback erased its "safe"
cushion once compressed to fit this account's real data constraints. Full detail:
[`candidate-strategy-backtest-results.md`](.claude/wiki/candidate-strategy-backtest-results.md).

**Backtest (52 weeks, real Alpaca historical option/equity data)**:

| Metric | Value |
|---|---|
| Trades/year | 11 |
| Win rate | 90.9% |
| Profit factor | 4.89 |
| Sharpe | 2.53 |
| Max drawdown | 1.99% |

SPY buy-and-hold returned +18.9% over the same window — expected, since this is a market-neutral
premium-selling strategy, not a directional bet on the index. The comparison that matters is
risk-adjusted return and drawdown control, where this strategy wins decisively. Sample sizes
(11-26 trades/year across candidates) are small enough that these numbers should be read as
backtest indicators, not proven point estimates — documented explicitly rather than oversold.

## AI Logic: Analyst → Governor → Executor

Three-layer pipeline, each with a strictly bounded role:

1. **Analyst** (Featherless AI, `deepseek-ai/DeepSeek-V3.2`) — reads the day's market snapshot and
   produces a bull case, bear case, and named-risk check. **Advisory only, never gates execution.**
   This was a deliberate design choice, validated by two live tests on the same day: once the
   analyst correctly flagged a real risk (an NFP-day expiry), once it fabricated a date fact
   (claimed the day after Labor Day when Labor Day had passed three days earlier). One real catch,
   one hallucination, same model, same day — exactly why its output is logged in full for
   audit/judging value but never allowed to block or approve a trade on its own.
2. **Governor** (deterministic Python) — the only layer that touches option math. Computes
   Black-Scholes IV/delta, selects real tradeable strikes from the live chain, and builds the
   exact order plan. LLMs are known to have ±15-40% error rates on option math done in token
   space — this layer exists specifically so the LLM never has to do that math.
3. **Executor** — a Pydantic-validated `CondorOrderPlan` (exactly 4 legs, valid OSI symbols, valid
   sides) is the only shape an order can take; anything else is rejected before it reaches the
   broker. Submitted via the Alpaca CLI as one atomic multi-leg (MLEG) limit order — all 4 legs
   fill together or none do.

## Risk Gates

| Gate | Threshold |
|---|---|
| Risk per trade | ≤2% of NAV |
| Margin utilization | ≤25% of buying power |
| Intraday drawdown | halt new entries at 3% |
| Total drawdown | kill switch (liquidate everything) at 6% |
| Bid-ask spread | reject any strike wider than 5% of mid, before it's even considered |
| 0-DTE positions | force-liquidated at 3:30 PM ET, ahead of assignment/after-hours tail risk |

Drawdown breakers are computed live from Alpaca's own portfolio-history endpoint every cycle, not
a separately-maintained state file — the account is judged fresh, so its full history *is* the
relevant window.

## Alpaca Infrastructure

- **Execution**: Alpaca CLI (`alpacahq/cli`), the only component allowed to touch the broker —
  satisfies the "MCP or CLI" requirement by construction, not by convention. Alpaca provides no
  hosted remote MCP server (self-hosting would add infra risk for no functional gain over the
  CLI here), so CLI was the deliberate choice.
- **Runtime**: GitHub Actions cron, every 15 minutes during market hours (13:00-20:00 UTC,
  Mon-Fri), running against the dedicated `PA3WNF5ZV8W3` account. Each cycle: check circuit
  breakers → manage any open position → evaluate a new entry if flat and not halted. Every
  branch writes a structured JSON audit event — including "nothing happened" cycles — committed
  back to the repo each run as the evidence trail for judging.
- **Event-date awareness**: SPY has daily expiries, not just weekly Fridays. The live target was
  deliberately shifted off Sep 4 (Non-Farm Payrolls day) to Sep 3 — the strategy's Black-Scholes
  strike selection assumes continuous price diffusion and has no way to price a scheduled jump
  event, so trading into one would mean the model is least trustworthy exactly when it matters
  most.
