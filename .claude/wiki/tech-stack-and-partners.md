# Tech Stack & Partners

## Lead partner: Alpaca

Alpaca is a brokerage platform providing access to financial markets through developer-friendly APIs. Securities trading via **Alpaca Securities LLC** (dba "Alpaca Clearing"); crypto trading via **Alpaca Crypto LLC**. Alpaca's Broker API is separately a full-stack brokerage infra product for fintechs/institutions (not the focus of this hackathon — the hackathon targets the direct Trading API).

### Core building blocks

| Component | What it is |
|---|---|
| **Trading API** | The programmable brokerage itself — place orders on US stocks, options, ETFs, and crypto. |
| **MCP server** | Lets an AI assistant (Claude, Cursor, VS Code, ChatGPT) interact with Alpaca's APIs through structured tools, in the paper-trading environment. |
| **Alpaca CLI** | Same trading functions from a terminal, structured JSON output. Built for long-running agent sessions, cron jobs, CI — lighter-weight than MCP. |
| **Paper trading environment** | Simulated funds with real market data. Free, no card required. |
| **Market Data API** | Real-time and historical market data. |
| **Alpaca Python SDK / JS SDK** | Language bindings for trading + market data. |

### Docs referenced on the page
- Getting Started (intro + first API integration)
- Alpaca Skills (AI-powered development resources)
- Trading CLI Documentation
- SDKs & OpenAPI Specs
- Multi-Agent AI Trading System guide (building an AI trading system with Alpaca — directly relevant to the "autonomous agent" requirement)

(Exact URLs weren't captured in the PDF text extraction — the page links to alpaca.markets and Alpaca Docs; re-check the live page or ask for these if we need direct links.)

## Technology partner: Featherless AI

- Serverless AI inference for open-source models — for agent reasoning, generation, research/automation/extraction agents.
- **Credits:** $25 per participant.
- **Access:** first-come, first-served.
- **Validity:** pay-per-request, active until credits run out.
- To be eligible for the Featherless-specific bonus (1st place $300 credit), the technology must actually be integrated into the submitted project — not just mentioned.

## Platform: lablab.ai / NativelyAI

- lablab.ai runs the hackathon platform, Discord community, submission flow, and judging logistics.
- NativelyAI is the parent group brand (per site footer, "© 2026 NativelyAI Inc.").

## Stack choices seen across competing teams

See [competing-projects.md](competing-projects.md) for the tech tags used by other teams (Anthropic Claude, Claude Code, Gemini, ChatGPT/OpenAI, AI/ML API, Groq, Featherless, Antigravity, LangGraph, Cursor, Codex, AgentOps, Reinforcement Learning, AWS, Vercel, Streamlit, GitHub Copilot, ElevenLabs, AI21 Labs — a wide mix, no single dominant stack).
