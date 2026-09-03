# Challenge & Requirements

## Main challenge: "Options Alpha Agents"

Build an autonomous AI trading agent designed to generate P&L using Alpaca's trading platform. Requirements:

- A clear, **testable** trading strategy.
- Demonstrate how the agent identifies opportunities, makes trading decisions, manages positions, and performs over the course of the competition.
- Free choice of approach — options, trading agents, portfolio income, or any other Alpaca-supported strategy — as long as the three core requirements below hold.

## Core requirements (mandatory, all three)

1. **Autonomous agents** — must build autonomous AI trading agents using Alpaca's Trading API (not a manual/human-in-the-loop-only tool).
2. **MCP or CLI** — project must utilize either Alpaca's MCP server or its CLI tools.
3. **Options trading** — all strategies must incorporate options trading (not pure equities/crypto).

## Account requirements

- **During development:** free to use any paper trading account to explore the API, MCP server, and CLI, and prototype strategies.
- **For final submission (judging):** must create a **brand-new, dedicated** Alpaca paper trading account specifically for this hackathon.
  - Projects run on an existing or reused paper account are **not eligible for judging**.
  - Competition account starting balance must be set to **$100,000**.
- Submission must include the **Alpaca paper trading account ID** used, so judges can pull trading activity and evaluate P&L directly.

## Additional deliverable

- A **one-page write-up** covering: AI logic, risk gates, and Alpaca infrastructure implementation.

## Extra challenge: Build in Public (social engagement)

- Share progress publicly on **X and LinkedIn** while building — process, reasoning, and setbacks included.
- Tag both **@lablabai** and **@AlpacaHQ** in posts.
- Up to **5 social media post links** can be submitted with the final project.
- Feeds into the separate [Social Engagement Prize](prizes-and-judging.md#social-engagement-prize) — 2 winning teams.

## Practical implications for our build

- **Risk gates** are explicitly named as a write-up requirement — build in position sizing / stop-loss / max-drawdown logic from the start, not as an afterthought; it's something judges will look for in the doc, not just infer from P&L.
- Since only a fresh paper account counts for judging, do all early prototyping on a throwaway account and provision the "real" submission account only once the strategy is stable — avoids polluting the judged trade history with test trades.
- Options-only constraint rules out pure stock-momentum or crypto-only strategies as the core loop; options can still be *informed* by equity/crypto signals, but the executed strategy must trade options.
