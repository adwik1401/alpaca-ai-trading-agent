# Build-in-Public Post Drafts

5 drafts spanning the build, for the hackathon's optional Social Engagement Prize. Tag
**@lablabai** and **@AlpacaHQ** on each. These are drafts for you to review/edit and post
yourself — nothing here has been published.

---

### 1. Kickoff

Building an autonomous options trading agent for the @AlpacaHQ AI Trading Agents Hackathon
(@lablabai) 🦙📈

The twist: the LLM never touches option math or picks a strike. It only debates market
regime for the audit trail — a deterministic Python layer does every real decision.

Building in public, let's go.

---

### 2. The bug that almost shipped a lie

Backtested 3 candidate strategies, got a Sharpe ratio of 11.8 on one. Should've been a
red flag immediately — instead I almost shipped it.

Turned out `metrics.py` was annualizing per-trade returns with a hardcoded √252, assuming
a trade every single day. The strategy actually trades ~11x/year. Real Sharpe: 2.53.

Same ranking, 4-5x smaller number, and now I actually trust it.

@AlpacaHQ @lablabai #buildinpublic

---

### 3. Backtested the "boring" strategy against 4 aggressive ones

Spent a day researching leveraged call diagonals, risk reversals, momentum verticals —
anything that might beat SPY's raw return, not just risk-adjusted.

Backtested all 4 against real historical option data. Every one lost to the market-neutral
iron condor I already had. The top-ranked "leveraged" pick was the *worst* performer once
tested for real.

Boring won. Real data doesn't care about a good story.

@AlpacaHQ @lablabai

---

### 4. Shipping the live agent

Live agent is running: Analyst (LLM, advisory only) → Governor (deterministic
Black-Scholes strike selection) → Executor (validated order → Alpaca CLI, atomic
multi-leg).

Every decision — including "did nothing this cycle" — gets logged and committed back to
the repo. Full transparency, nothing hidden.

Running unattended on GitHub Actions cron now. 🤖

@AlpacaHQ @lablabai

---

### 5. Wrap-up

Submitted my @AlpacaHQ AI Trading Agents Hackathon project (@lablabai): a market-neutral
SPY iron condor agent, backtested at Sharpe 2.53 / 90.9% win rate over real historical
data, running unattended with a full public audit trail.

Repo: github.com/adwik1401/alpaca-ai-trading-agent

Biggest lesson: the strategy that survives contact with real data usually isn't the
exciting one.
