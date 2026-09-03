# Trading Strategy & Architecture Research (2025-2026)

Research delegated to Antigravity CLI on 2026-09-01, covering: options strategies for autonomous LLM agents, risk gate design, underused signal sources, and production best practices. Full dossier saved by Antigravity at `C:\Users\Adwik\.gemini\antigravity-cli\brain\57a88a64-20ab-42c4-b6fb-afdef12cd65a\alpaca_ai_options_trading_research.md` (local machine, not in this repo).

## 1. Options strategy playbook for a 7-day window

| Strategy | Core mechanism | Alpaca MLEG implementation |
|---|---|---|
| Volatility Risk Premium (VRP) harvesting | Harvests IV > realized-vol spread via high-IV-rank credit spreads | 4-leg delta-neutral Iron Condor (3–7 DTE) |
| Dealer Gamma (GEX) positioning/pinning | Identifies call/put walls & zero-gamma flip levels | Mean-reverting spreads in +Γ; breakout debit spreads in -Γ |
| Earnings IV crush (event-driven) | Exploits overnight IV collapse when implied move > historical | Defined-risk credit spreads/iron condors, closed next AM |
| Asymmetric catalyst momentum | LLM extracts breaking filings/news before IV reprices | 2-leg OTM debit vertical call/put spreads |

### What fails for LLM agents specifically
- **Direct LLM option math** — LLMs can't reliably do Black-Scholes/Greeks in token space (±15–40% error). Never let the LLM compute prices/Greeks.
- **Hallucinated strike symbology** — LLMs invent strikes that don't exist on the exchange.
- **Unbounded tail risk** — naked short options (short strangles/naked puts) risk catastrophic liquidation in tail events.
- **Market orders on illiquid chains** — crossing >$0.10 spreads forfeits 30–50% of theoretical edge immediately.

### What works
- **LLM as qualitative synthesizer / regime classifier** — analyze macro/earnings/filings/news to tag a market regime (`HIGH_IV_RANGEBOUND`, `BREAKOUT_EVENT`, `VOLATILITY_EXPANSION`), not to price anything.
- **Multi-agent dialectical debate** — separate Bull / Bear / Risk-Arbiter subagents to reduce single-model bias (see [TradingAgents](https://arxiv.org/abs/2412.18608), [MarketSenseAI 2.0](https://arxiv.org/abs/2502.00415)).
- **Deterministic Python solver for strike selection** — LLM outputs qualitative constraints only (delta target range, min net credit, max DTE); a NumPy/Python engine scans the live Alpaca chain for exact valid OSI contract symbols.

## 2. Risk gate architecture — "Zero-Trust Execution Pipeline"

Raw LLM output never touches the broker directly. Proposed pipeline:

```
LLM Agent Consensus → [1] Pydantic Schema Validator → [2] Exposure & Kelly Sizer
→ [3] Drawdown & Spread Gate → Alpaca MCP/MLEG Order
(any layer can Reject/Retry; layer 3 can trip a Kill Switch / Liquidate)
```

1. **Schema & contract validation** (Pydantic/Instructor) — enforce typed fields (strategy, ticker, expiration, legs with exact OSI format `[Ticker][YYMMDD][C/P][00000000]`, limit price); cross-check every leg against Alpaca's live options API (`get_option_contracts`) for active status/open interest before building the order.
2. **Position sizing & margin caps** — fractional Kelly, risk per trade ≤1.5–2.0% of NAV; gross margin on multi-leg spreads ≤25% of buying power.
3. **Circuit breakers** — intraday drawdown breaker at 3% (halt new entries, defensive monitoring only); total drawdown breaker at 6% (hard kill switch: close all short legs, cancel open orders, go to cash); bid-ask spread filter (discard if (ask-bid)/mid > 5%); zero-DTE pin-risk auto-liquidation of expiring short legs at 3:30 PM ET on expiration day.
4. **Reference frameworks**: [Instructor](https://github.com/jxnl/instructor) / [Pydantic v2](https://docs.pydantic.dev/) for strict response models; [NVIDIA NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) for action enforcement; [TauricResearch TradingAgents](https://github.com/TauricResearch/TradingAgents) for consensus architecture.

## 3. Distinct/underused signal sources

| Signal | Source (free/cheap) | Alpha mechanism |
|---|---|---|
| Real-time SEC EDGAR (Form 4 cluster buys >$500k, 8-K item 1.01) | [SEC Submissions API](https://www.sec.gov/edgar/sec-api-documentation) (free) | LLM parses within seconds → cheap directional call spreads before IV rises |
| Dealer Gamma Exposure (GEX) | Computed from Alpaca options chain (OI × Γ × 100 × spot) | GEX>0 → pinned market → sell iron condors; GEX<0 → unpinned → directional debit spreads |
| FRED net Fed liquidity (WALCL − TGA − RRP) | [fredapi](https://fred.stlouisfed.org/docs/api/fred/) (free key) | 5-day liquidity delta shows >0.75 correlation with broad options skew |
| Implied vs. realized vol spread | Alpaca Market Data + yfinance/OpenBB | High positive spread → options overpriced → favors theta selling |
| Earnings implied-move mismatch | Yahoo Finance / Finnhub free tier | Compare priced implied move vs. historical realized move → systematic IV overpricing |
| Cross-asset vol term structure (VIX/VXV) | CBOE via Yahoo/OpenBB | Contango (<0.95) → calm, premium-selling; backwardation (>1.05) → hedge/long-vol |

## 4. Production architecture & evaluation best practices

**Pattern: "LLM-as-Analyst, Quant-as-Governor, Code-as-Executor"**
- Analyst layer (fast reasoning LLM): macro/news ingestion, bull/bear debate, regime classification.
- Governor layer (deterministic NumPy): Black-Scholes Greeks, VRP/GEX solver, Kelly sizing.
- Executor layer: Pydantic verification, MLEG payload builder, Alpaca FastMCP/CLI atomic limit order.
- Orchestration via [LangGraph](https://github.com/langchain-ai/langgraph) or [FastMCP](https://github.com/jlowin/fastmcp) connected to the [Alpaca MCP Server](https://github.com/alpacahq/alpaca-mcp-server).
- Always use `OrderClass.MLEG` + `LimitOrderRequest` for multi-leg spreads — atomic fill (all legs or none) at net credit/debit limit.

**Latency/cost**: tiered model routing — cheap/fast models (Gemini 1.5 Flash, Claude Haiku) for continuous polling/news-scanning; heavy models (Gemini 1.5 Pro, DeepSeek-R1) only triggered on anomaly detection or position rebalancing. Event-driven execution (market open, 15-min intervals, news webhooks) instead of a continuous generation loop — controls both cost and latency risk.

**Evaluation metrics judges/serious builders track** (beyond raw P&L):

| Metric | Target | Why it matters |
|---|---|---|
| Sortino / Sharpe | Sortino >2.5, Sharpe >2.0 | Risk-adjusted consistency, not lucky high-beta bets |
| Max drawdown | <4.0% | Proves risk gates actually work |
| Profit factor | >1.8 | Confirms a real mathematical edge |
| Execution quality / slippage | <$0.02 from midpoint | Proves the limit-pricing engine works |
| Audit trace | 100% structured JSON logs | Every order traceable to bull thesis, bear counter, risk-gate sign-off |

## Key sources
- [TradingAgents (Tauric Research, arXiv:2412.18608)](https://arxiv.org/abs/2412.18608) — multi-agent dialectical debate architecture
- [MarketSenseAI 2.0 (arXiv:2502.00415)](https://arxiv.org/abs/2502.00415)
- [FinRobot (AI4Finance, arXiv:2405.14767)](https://arxiv.org/abs/2405.14767)
- [Alpaca MCP Server](https://github.com/alpacahq/alpaca-mcp-server)
- [alpaca-py options examples](https://github.com/alpacahq/alpaca-py/tree/master/examples/options)
- [Alpaca Trading API docs](https://docs.alpaca.markets/)
- [SEC EDGAR Submissions API](https://www.sec.gov/edgar/sec-api-documentation)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
- [OpenBB](https://github.com/OpenBB-finance/OpenBB)
- [Instructor](https://github.com/jxnl/instructor) / [Pydantic v2](https://docs.pydantic.dev/)
- [NVIDIA NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails)

## Caveats
- This is Antigravity/Gemini-sourced secondary research, not verified firsthand — treat specific numeric thresholds (Kelly %, drawdown %, Sharpe targets) as reasonable starting defaults to tune, not settled facts.
- "1.5 Flash" / "1.5 Pro" model naming reflects the source material's framing of tiered cost/latency routing (cheap-fast vs. heavy-reasoning) — re-check current model lineups before locking in a specific model ID.
