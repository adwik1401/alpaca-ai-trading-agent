# Architecture Decisions

## Team: solo

Adwik is building this solo. Simplifies prize-payee designation (no split needed) and team registration on lablab — no multi-member coordination overhead.

## LLM provider: Featherless AI (free hackathon credits)

- Featherless AI gives $25/participant in free inference credits, pay-per-request, first-come-first-served (see [tech-stack-and-partners.md](tech-stack-and-partners.md)).
- API is **OpenAI-compatible** (`/v1/chat/completions`), so any OpenAI-SDK-based agent code works with a base-URL swap. Confirmed via [featherless.ai/docs](https://featherless.ai/docs) on 2026-09-01.
- Hosts open-source model families: **Qwen, Llama, Mistral, DeepSeek, RWKV** (including "QRWKV" linear-transformer models). Supports **tool calling** and vision; embeddings available separately.
- **Implication for tiered model routing** (per [trading-strategy-and-architecture-research.md](trading-strategy-and-architecture-research.md)): use a smaller Qwen/Llama variant for cheap continuous polling/news-scanning, and a larger DeepSeek/Qwen variant for the heavier bull/bear debate + regime classification step. Exact model IDs and current pricing need a check against the live [Featherless models page](https://featherless.ai/models) and [pricing](https://featherless.ai/#pricing) once we scaffold the code — this was a docs-overview fetch, not a full pricing/rate-limit audit.
- **Open risk**: $25 in pay-per-request credits could run out mid-competition if the polling cadence is too aggressive (e.g. every 1-5 min for 7 days across multiple model calls per cycle). Budget the call frequency deliberately — this is a hard cap, not a soft one, since it's "active until credits run out."

**Confirmed 2026-09-01** (keys tested live against `https://api.featherless.ai/v1/models`, 21,906 models available). Picked two official (non-finetuned/non-abliterated) models for the tiered routing pattern, to avoid unpredictable behavior from community variants:

| Tier | Model | Pricing (prompt / completion per token) | Context |
|---|---|---|---|
| Fast/cheap (polling, news-scanning) | `meta-llama/Meta-Llama-3.1-8B-Instruct` | $0.000000035 / $0.000000065 | 32,768 |
| Heavy reasoning (bull/bear/risk debate) | `deepseek-ai/DeepSeek-V3.2` | $0.0000002995 / $0.00000045 | 131,072 |

Both are cheap enough that the $25 cap is unlikely to bind unless polling is very aggressive — but still budget call frequency deliberately (see risk above).

## Hosting/runtime split: GitHub Actions (agent) + Netlify (dashboard) — NOT Netlify for the trading engine

User asked whether Netlify alone would work. Verified against primary sources on 2026-09-01:

- **Why not Netlify for the actual trading loop**: Netlify Functions are AWS-Lambda-based with short execution windows (seconds, or up to ~15 min for background/scheduled functions) and no persistent filesystem/state between invocations. More importantly, the CLI tool we need to satisfy the hackathon's "MCP or CLI" requirement (see below) is a Go binary — awkward to bundle into a Node-oriented serverless function, versus trivial in a full VM.
- **Why GitHub Actions for the trading engine instead**:
  - `alpaca/cli` ([github.com/alpacahq/cli](https://github.com/alpacahq/cli)) is explicitly "Built For Agents": no interactive prompts, designed for scripts/CI/cron, auths via `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` env vars (paper trading by default — live requires explicit opt-in). This is a direct match for a scheduled CI job.
  - A GH Actions `schedule:` (cron) workflow gives a full Ubuntu runner — trivial to install the Go CLI binary or run Python (for the LLM/analysis/risk-gate code), no serverless packaging constraints, jobs can run far longer than needed, and it's free for the public repo we're required to have anyway.
  - State/audit trail (structured JSON logs of every decision, required for the judging "dialectical audit trace") can be committed back to the repo each run, or written to a lightweight external store — simpler within a full VM than inside stateless Lambda-style functions.
- **Why Netlify still has a role**: the submission requires a "Demo application platform / Application URL." A Netlify site (the user is already set up with Netlify across other portfolio projects) is a good fit for a **read-only dashboard** — P&L curve, current positions, and the audit trail of agent reasoning — fed by data the GH Actions job writes out (e.g. to a JSON file in the repo, or a small Supabase/DB table if we want live updates rather than rebuild-on-push).

**Decision**: trading engine runs on GitHub Actions cron, driven by Alpaca CLI; Netlify hosts the public demo/dashboard reading the engine's output. Revisit only if GH Actions' scheduling granularity (min ~5 min intervals in practice, not to-the-second) turns out too coarse for the chosen strategy's required check-in frequency.

## MCP vs CLI: going with CLI

- Alpaca's official MCP server ([github.com/alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server)) is designed for **interactive AI-assistant clients** (Claude Desktop, Cursor, VS Code, ChatGPT) via stdio — spun up per-session by the assistant. Alpaca's own docs state: *"Alpaca does not provide a hosted remote MCP server"* — self-hosting would be required for any unattended/remote use, adding real infra overhead for no functional benefit over the CLI in our case.
- The CLI is purpose-built for exactly our use case (autonomous, scheduled, unattended). Using it satisfies the hackathon's core requirement #2 ("MCP or CLI") with far less integration risk.
- Confirmed the CLI supports options directly: `alpaca option`, `data option` command groups, plus a raw `alpaca api [METHOD] <path>` escape hatch for anything not yet wrapped.

## Strategy candidate B: GEX positioning renamed to "Put-Call Skew Regime"

Confirmed 2026-09-01: Alpaca's data API has **no open-interest field anywhere** — not in historical option bars, not in the live options snapshot endpoint (`/v1beta1/options/snapshots/{underlying}`, which returns `dailyBar`, `greeks`, `impliedVolatility`, `latestQuote`, `latestTrade`, `minuteBar`, `prevDailyBar` — no OI). True dealer Gamma Exposure (`GEX = OI × Gamma × Spot² × 0.01`) is mathematically impossible to compute from Alpaca's own data, live or historical, without sourcing OI elsewhere (e.g. a paid OPRA-derived feed) — not worth adding another vendor dependency with ~3 days left.

**Substitution**: put-call **IV skew** as the regime signal instead — a real, well-established options positioning indicator (steepening skew = rising hedging demand/downside fear, flattening/inverted = market complacency), computed the same way as the VRP signal (Black-Scholes inversion on real historical option prices), so it requires no new data source. This keeps all 3 backtest candidates grounded in real market data rather than a synthetic or fabricated proxy.

## Live agent: CLI syntax, event-date targeting, and the LLM's advisory-only role

Confirmed live against the dev paper account on 2026-09-02:

- **Alpaca CLI multi-leg syntax**: `alpaca order submit --order-class mleg --type limit --limit-price <net> --time-in-force day --qty <n> --legs '[{"symbol":...,"side":"sell"|"buy","ratio_qty":"1"}, ...]'`. All 4 legs of a real test iron condor were `accepted` server-side. Downloaded the CLI as a prebuilt Windows binary from `github.com/alpacahq/cli` releases (no Go toolchain available) — not committed to the repo (9.5MB binary); the GitHub Actions workflow fetches it fresh each run.
- **SPY has daily expiries**, not just weekly Fridays — this mattered a lot: with only ~2.5 days left, "next Friday" (Sep 4) happens to be Non-Farm Payrolls day (first Friday of the month), a major scheduled volatility catalyst. Our strike selection is Black-Scholes delta-targeting, which assumes continuous price diffusion and cannot price jump/gap risk from a scheduled binary event — trading into NFP would mean our own probability model is least trustworthy exactly when it matters most. **Decision: target 2026-09-03 (Thursday) instead of 2026-09-04** — dodges NFP entirely, at the cost of a shorter (1 DTE) window. Implemented as `agent.governor.next_valid_expiry()` + `config.AVOID_EXPIRY_DATES`.
- **The LLM analyst layer is advisory-only, not a gate** — confirmed by two live test failures on the same day:
  1. First test: analyst recommended "abstain" citing "Non-farm payrolls release on expiration day" for the *original* Sep 4 target — this one was actually **correct and useful** (Sep 4 genuinely is NFP day), and directly informed the decision above.
  2. Second test (after switching to Sep 3): analyst recommended "abstain" citing "September 3rd is the day after Labor Day" — this is **wrong**; Labor Day 2026 was Aug 31 (Monday), three days before Sep 3, not one.
  One real catch, one fabrication, same day, same model. This is exactly why the design keeps the LLM's recommendation logged in full (real audit/judging value) but never gating execution — only the deterministic VRP+skew signal and the circuit breakers in `risk_gates.py` decide go/no-go. A human (or a more reliable calendar tool call) should still sanity-check any analyst risk_note that claims a specific dated fact before treating it as ground truth.

## Reference implementations worth reviewing before scaffolding

- [alpacahq/options-wheel](https://github.com/alpacahq/options-wheel) — a full runnable wheel-strategy template (uv-based venv, `config/params.py` for tunables, `config/symbol_list.txt` for universe, structured JSON strategy logging via `--strat-log`, `--fresh-start` flag to liquidate and start clean). Not our strategy (wheel vs. our VRP/iron-condor lean) but a good scaffold reference for config structure and logging conventions.
- [alpacahq/gamma-scalping](https://github.com/alpacahq/gamma-scalping) — runnable template for gamma scalping, relevant if we lean into the GEX/dealer-positioning angle from the research.
