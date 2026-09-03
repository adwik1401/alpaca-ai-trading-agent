# Alpaca AI Trading Agent

An autonomous AI options trading agent built for the [Alpaca AI Trading Agents Hackathon](https://lablab.ai). Runs unattended on a schedule, trades real (paper) SPY iron condors based on a backtested volatility-risk-premium + skew signal, and logs every decision it makes.

**Read [WRITEUP.md](WRITEUP.md) for the full strategy rationale, risk gates, and architecture writeup** (the hackathon's required one-page deliverable). This README covers how the project is put together and how to run it.

**Live account:** `PA3WNF5ZV8W3` (Alpaca paper trading, $100,000 starting balance)

## Architecture

Three-layer pipeline, each with a strictly bounded role — the LLM never touches option math or picks a strike, and no order reaches the broker without passing through deterministic validation:

```
Analyst (LLM, advisory only)  →  Governor (deterministic strike selection)  →  Executor (validated order → Alpaca CLI)
```

Runs on a GitHub Actions cron schedule (`.github/workflows/trading-agent.yml`), every 15 minutes during US market hours, and commits a structured JSON audit log (`agent/audit_log.jsonl`) back to this repo after every cycle — that log is the real-time evidence trail of every decision the agent has made.

## Project structure

```
agent/            Live trading agent: config, analyst, governor, executor, risk_gates, audit_log
backtest/
  strategies/      Weekly candidate strategies (VRP, skew regime, hybrid) - see backtest-results.md
  intraday/        0DTE intraday candidates, incl. the strategy backing backtest/tuning/
  candidates/      4 researched "return-competitive" alternatives to the live strategy
  tuning/          Autoresearch-inspired parameter search tool for the 0DTE Iron Condor strategy
.github/workflows/ CI: the scheduled trading cron
.claude/wiki/      Full research, backtest results, and architecture-decision history
.claude/plans/     Build plan and progress tracking
```

## Running it

```bash
pip install -r requirements.txt
cp .env.local.example .env.local   # fill in Alpaca + Featherless API keys

# Run one live agent cycle (paper trading by default)
python -m agent.run_agent

# Re-run a strategy backtest against real historical Alpaca data
python -m backtest.run_backtest 52        # weeks of lookback
python -m backtest.intraday.run_intraday_backtest 126   # trading days
```

`AGENT_ACCOUNT=submission` switches the live agent to the dedicated judging account instead of the dev account — see `agent/config.py`.

## Why this strategy

Market-neutral weekly SPY iron condors, gated by a volatility-risk-premium signal and a skew-regime filter, backtested at Sharpe 2.53 / 90.9% win rate / 1.99% max drawdown over a real 52-week window. Four directional, return-competitive alternatives were researched and backtested specifically to check whether something could beat SPY's raw return — none did once tested against real data, and the top-ranked candidate was the worst performer of the four once compressed to fit this account's real data constraints. Full detail in [`.claude/wiki/backtest-results.md`](.claude/wiki/backtest-results.md) and [`.claude/wiki/candidate-strategy-backtest-results.md`](.claude/wiki/candidate-strategy-backtest-results.md).
