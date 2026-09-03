# Competing Projects (public leaderboard snapshot, 2026-09-01)

Captured from the "Submitted concepts, prototypes and pitches" section of the hackathon page as of the PDF snapshot date. Enrollment showed **3,397 approved participants**. This list is whatever the page had rendered/paginated at snapshot time — likely not exhaustive, and will grow before the Sep 4 deadline. Treat as a competitive scan, not a final leaderboard.

## Strategy patterns worth noting

- **Multi-agent / debate architectures** are common: TradeCouncil (multi-agent options), Debatte (5 LLM analysts debating theses), OptionFlow Sentinel (5-agent LangGraph "hedge fund"), AlphaSwarm Sovereign (adversarial dialectic multi-agent).
- **Human-in-the-loop / bounded-trust framing** shows up repeatedly as a differentiator: Vetoed ("AI is the least-trusted component"), BABIL (human-in-the-loop, separates reasoning from execution), AEGIS-Q ("bounded AI selects a pre-validated..."), ThetaTrap ("Bounded..."), Horizon Blackline ("governed autonomous... LLM proposes, [something else disposes]"). Several teams are explicitly designing around "don't fully trust the LLM to execute" — worth considering for our own risk-gate design since judges call out risk gates explicitly.
- **Evidence/news-driven signals**: Crowd Excess (attention vs. objective news divergence), NewsFlow Trader (LLM-driven news trading), EdgeStack ("evidence opens the door to..."), Odysseus (turns any AI agent into an autonomous trading researcher).
- **Options-specific mechanics named**: IV Rank Premium (IV-rank options selling), Vega (SPY convexity via options), Pin Desk (dealer gamma / hedging pin mapping), VRP Engine (variance risk premium harvesting), Futarchists Options (modular strategy discovery), Options Sniper (Bull Call Spreads across 7 tickers), a continual learning agent using hourly volatility forecasts + options.
- **Dominant underlying**: SPY shows up by name multiple times (SPY Sentinel AI, AlphaPilot AI, Vega) — narrow, liquid, options-friendly index proxy seems a popular default choice.

## Team roster (name — pitch — tech tags)

| Team / Project | One-line pitch | Tech tags |
|---|---|---|
| Crowd Excess | Auditable AI agent detecting when attention/price outrun objective news | Alpaca, OpenAI |
| TradeCouncil | Multi-agent options trading system using Featherless AI | Alpaca, Featherless AI Studio |
| Ichika (SilverCrane) | — | — |
| IV rank Premium... (Elvera) | Automated options-selling agent on Trading API + Market Data API | Alpaca, AgentOps |
| Aegis: a trading agent... (Aegis Labs) | LLM agents good at plausible trades, bad at refusing bad ones (risk framing) | Alpaca, Gemini 3 Flash, Claude Code, +1 |
| Strike Sentry (Strike-sentry) | Options agent researching live market data and executing | AI/ML API, Gemini AI, Groq, +2 |
| EdgeStack: Evidence-... (EdgeStack AI) | Autonomous agent built on "evidence opens the door to..." | Alpaca, ChatGPT, Claude Code, +2 |
| Circuit Breaker | Fully autonomous agent that monitors, decides, executes | Anthropic Claude, Alpaca |
| Vetoed (Vetoed) | Options agent where AI is the least-trusted component; sells... | Alpaca, Claude Code, Featherless, +1 |
| ORACLE: 24/7... | 24/7 autonomous options intelligence, agents reason | AI/ML API, Alpaca |
| VANGUARD OS (Vanguard OS) | Autonomous agent combining multiple approaches | AI/ML API, Alpaca, Anthropic Claude, +2 |
| Horizon Blackline | Governed autonomous options-trading agent; LLM proposes | Alpaca, Anthropic Claude, AWS, +1 |
| Debatte -- Five... (Debatte - Team) | 5 LLM analysts w/ separated data views debate theses, deterministic... | Claude Code, Alpaca, Anthropic Claude, +2 |
| AegisAlpha --... (Zenith) | Combines parallel... | Alpaca, Anthropic Claude |
| OptionFlow Sentinel | Multi-tenant AI hedge fund, 5-agent LangGraph | Alpaca, Antigravity, Gemini 3 Pro, Generative Agents |
| AegisAlpha:... (Returnee) | Multi-agent options desk powered by Alpaca FastMCP, Qwen | Alpaca, Featherless, Vercel |
| Visheshak (visheshak) | Autonomous, defined-risk options agent ("the discerner") | Gemini AI, Anthropic Claude, Alpaca |
| AI Stock Trading Agent (ShubhpreetAIAdda#1) | Analyzes stock market data | ChatGPT, AI/ML API, Gemini AI |
| TradeMind - AI Option... (TradeMind) | Autonomous AI options trading engine, deterministic... | Alpaca, Claude Code |
| Futarchists Options (Futarchists) | Modular strategy discovery and execution system | Alpaca, Anthropic Claude, ChatGPT, +4 |
| SOGNO Options Agent | Autonomous options agent extending technical + [signal engine] | Claude Code, Alpaca, Anthropic Claude |
| Autonomous Multi-... (AdventurousCat) | 4-agent options trading engine, Level-3 MLEG... | Alpaca, Featherless |
| Vermiliion (Vermilion) | Self-auditing agent; DeepSeek scores a 13-symbol... | Alpaca, Codex, Cursor, +1 |
| Autonomous Unified... (ai-champians) | AI agents given real-world power — moving money, executing trades | AI/ML API, AIML, Groq, +2 |
| Cloudrise Alphaca Ai... (CloudRise) | Sees the market, tells you the result | AI21 Labs |
| KRAKN.AI | Autonomous agent that finds, executes, manages | (unspecified) |
| AEGIS-Q | Bounded AI selects a pre-validated... | (unspecified) |
| Aussie trading | — | Anthropic Claude, Alpaca |
| Team V | — | Alpaca, OpenAI, ElevenLabs |
| BABIL -- Human-in-th... (BABIL) | Human-in-the-loop options agent, separates AI reasoning from execution | Alpaca, AI/ML API |
| VRP Engine:... (Participant) | Harvests variance risk premium | Cursor, Alpaca |
| SPY Sentinel AI | SPY research agent, market structure + validation | Alpaca, GitHub Copilot |
| ThetaTrap -- A Bounde... (Neural Point Analytica) | Qwen + Alpaca's official MCP server, earnings-risk evaluation | Codex, Alpaca, Featherless |
| AlphaPilot AI (Quantum Coders) | SPY market analysis paper-trading system | Alpaca, Auto-GPT, AI/ML API, +5 |
| VibeHedge:... (ShinyDataTech) | ForecastAgent xLSTM time-series | Alpaca, Reinforcement Learning, Antigravity |
| AlphaSwarm Sovereign | Multi-agent quant hedge fund SaaS, adversarial dialectic | Alpaca, AI/ML API, AI Studio, +5 |
| NewsFlow Trader (cubiczan) | Autonomous LLM-driven news trading agent | Alpaca |
| Odysseus - AI-Powere... (Odysseus) | Turns any AI agent into an autonomous trading researcher | Codex |
| Vega -- autonomous... (isquividet) | Buys SPY convexity via Alpaca's MCP server | Alpaca |
| Pin Desk (Gasbin) | Maps dealer gamma to find hedging pins | Alpaca, Groq, Streamlit |
| a continual learning... (trueintrinsics-agent) | Pure-options agent, PX5000 hourly volatility forecasts | AgentOps, AI/ML API, Reinforcement Learning |
| Options Sniper - Tradi... (primehack security team) | Scans 7 tickers, builds scored Bull Call Spreads | Alpaca |
| AlphaGuard AI:... (AlphaGuard AI) | Multi-agent algorithmic trading desk, Gemini 2.5 Flash | Alpaca, Gemini AI |

## Teams looking for members (as of snapshot)

- **Pantherzz** — "I'm about to find an edge"
- **Bagholders** — "The fund for bagholders"
- **ShubhpreetAIAdda** — "Building the trading app"
- **GUAC...** (name truncated in extraction) — one more team listed as "Autonomous AI trading agent with Claude MCP..."

## Caveats on this data

- Text was extracted from a saved PDF of a JS-rendered page; several pitch descriptions and a few team names are truncated ("...") where the page cut them off, and a couple of card layouts overlapped in the extraction (e.g. row with "ai-champians" / "CloudRise"). Don't treat truncated fragments as verified facts — re-visit the live page if exact wording matters for a specific competitor.
- This is a snapshot, not final. Team count will grow and any given team's approach may change substantially by the Sep 4 deadline.
