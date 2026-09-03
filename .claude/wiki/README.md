# Alpaca AI Trading Agents Hackathon — Wiki Index

Research and working notes for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon), run on the lablab.ai platform in partnership with Alpaca (AlpacaDB, Inc.). Source: the competition landing page, saved as [Alpaca AI Trading Agents Hackathon AI Hackathon _ lablab.ai.pdf](../../Alpaca%20AI%20Trading%20Agents%20Hackathon%20AI%20Hackathon%20_%20lablab.ai.pdf) on 2026-09-01.

## Competition context

- **Theme:** code the next generation of algorithmic trading — build autonomous AI trading agents on Alpaca's programmable brokerage.
- **Format:** fully online, 7 days, **28 Aug – 4 Sept 2026**. Kickoff Aug 28, 8:30 PM IST; submissions close Sep 4, 8:30 PM IST.
- **Prize pool:** $6,300 total (see [prizes-and-judging.md](prizes-and-judging.md)).
- **Lead partner:** Alpaca (brokerage infra — Trading API, MCP server, CLI, paper trading). **Tech partner:** Featherless AI ($25/participant inference credits). **Platform:** lablab.ai / NativelyAI.
- **Hard constraint:** everything runs against Alpaca's **paper-trading environment** — no real capital. Final submission must use a **brand-new, dedicated** paper account (existing/reused accounts are disqualified from judging).
- **Non-negotiable scope:** the agent must (1) be autonomous, (2) use Alpaca's MCP server or CLI, and (3) incorporate **options trading**. Missing any one of these three likely fails the core requirements, not just loses points.

## Pages

- [Challenge & Requirements](challenge-and-requirements.md) — the "Options Alpha Agents" challenge, account rules, what's mandatory vs. optional
- [Prizes & Judging](prizes-and-judging.md) — prize breakdown, judging criteria, payment/tax terms
- [Submission & Guidelines](submission-and-guidelines.md) — how to participate, team rules, submission checklist, event schedule
- [Tech Stack & Partners](tech-stack-and-partners.md) — Alpaca Trading API/MCP/CLI, Featherless AI credits, SDKs and docs
- [Competing Projects](competing-projects.md) — teams/projects visible on the public leaderboard page, for competitive scan of strategy/stack choices
- [Trading Strategy & Architecture Research](trading-strategy-and-architecture-research.md) — options strategies, risk gate design, underused signal sources, and production best practices for autonomous trading agents
- [Architecture Decisions](architecture-decisions.md) — team/LLM/hosting decisions and why (solo, Featherless AI, GitHub Actions + Netlify split, CLI over MCP)
- [Backtest Results & Strategy Selection](backtest-results.md) — real historical-data backtest of 3 candidate weekly strategies; Hybrid VRP+Skew selected as the live strategy
- [Intraday Strategy Research](intraday-strategy-research.md) — industry-standard 0DTE/intraday strategies researched as a higher-frequency alternative
- [Intraday Backtest Results](intraday-backtest-results.md) — 6-month backtest of all 4 intraday candidates; none beat weekly Hybrid, decision reaffirmed

## Log

See [log.md](log.md) for a running history of research/analysis sessions.
