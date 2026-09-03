# Alpaca AI Trading Agent — Build Plan

**Overall Progress:** `79%` (33/42 checkboxes)

> **2026-09-02 update: ~2.5 days remain** until the Sep 4, 8:30 PM IST deadline (was ~3.5 days when this plan was created). Phase 2 scope must stay tight — no gold-plating.
>
> **2026-09-03 update: ~1 day remains.** Critical path is now Step 7 (done) → Step 8 (GH Actions cron) → Phase 3 (dashboard, can be minimal) → Phase 4 (write-up, required). Everything else is cut if time runs short.

## TLDR
Backtest 4 candidate options strategies against real historical Alpaca options data, pick the strongest, then build and run a live autonomous agent on a fresh Alpaca paper account for the remaining runway of the Alpaca AI Trading Agents Hackathon (deadline: **Sep 4, 2026, 8:30 PM IST — only ~3.5 days from today, 2026-09-01**). Ship a public GitHub repo, a Netlify demo dashboard, and the full submission package.

## Delegation Pipeline
Each code phase follows this portfolio's standard pipeline:
```
/execute → /run-code (Codex, if tests exist) → /fix-bug (Codex, if failures) → /run-code (verify) → /review
```
- Before invoking Codex: TodoWrite entry + `[DELEGATING → Codex /run-code]` or `[DELEGATING → Codex /fix-bug]` announcement.
- After each delegation: append a row to `.claude/agent-log.md`.
- No conventional unit-test suite for a trading strategy — `/run-code` here means running the backtest/agent script and checking it executes cleanly with sane output, not a pass/fail test suite.
- Manual/no-code phases (account setup, submission packaging) are **Claude-managed** — no sub-agent needed.

## Critical Decisions
(carried over from `.claude/wiki/architecture-decisions.md` and `trading-strategy-and-architecture-research.md`)
- **LLM**: Featherless AI — OpenAI-compatible API, free $25 hackathon credit, hosts Qwen/Llama/Mistral/DeepSeek with tool calling.
- **MCP vs CLI**: Alpaca CLI (Go binary, built for cron/scripts/agents) — not MCP, since Alpaca provides no hosted remote MCP server and MCP is designed for interactive assistant sessions.
- **Runtime split**: GitHub Actions scheduled workflow runs the trading engine; Netlify hosts only the read-only demo dashboard.
- **Risk architecture**: LLM-as-Analyst (regime + bull/bear debate) → Quant-as-Governor (deterministic Python: Greeks, strike selection, Kelly sizing) → Code-as-Executor (Pydantic-validated, atomic Alpaca MLEG limit orders). The LLM never does option math or picks exact strikes.
- **Strategy selection method**: backtest-and-pick, not live A/B — confirmed there isn't enough live runway left (~3.5 days) to compare strategies by paper-trading them for days.

## Tasks

### Phase 0 — Accounts & Access (blocking — do first)
> Claude-managed, no sub-agent — but every later phase is blocked on this

- [x] 🟩 Create an Alpaca paper trading account for dev/backtesting use (account `PA37YZBHY6Q7`, options approved level 3, $100k default paper balance)
- [x] 🟩 Generate Alpaca paper API key + secret, supply as env vars — verified working via `/v2/account`
- [x] 🟩 Create a Featherless AI account + API key — verified working, 21,906 models available; picked `meta-llama/Meta-Llama-3.1-8B-Instruct` (fast/cheap tier) and `deepseek-ai/DeepSeek-V3.2` (heavy reasoning tier)
- [x] 🟩 Confirm or create the public GitHub repository this project will live in — created 2026-09-03: **https://github.com/adwik1401/alpaca-ai-trading-agent** (public), initial commit pushed (77 files)
- [ ] 🟥 Confirm Netlify account access (likely already available from other portfolio projects)

### Phase 1 — Backtest Harness & Strategy Selection (today — hours, not days)
> `[DELEGATING → Codex /run-code]` (scripts execute cleanly) → `[DELEGATING → Codex /review]` (sanity-check backtest math/logic)

- [x] 🟩 **Step 1: Data access spike** — confirmed on 2026-09-01: Alpaca's historical option bars endpoint (`/v1beta1/options/bars`) returns real daily OHLCV for already-expired SPY contracts (full contract lifetime); SPY equity bars available back to Jan 2026 (8 months). Plan A (real historical option prices + our own Black-Scholes implied-vol inversion) confirmed viable — synthetic fallback not needed.
- [ ] 🟥 **Step 2: Implement 3 candidate strategies as backtest modules** (SPY as default underlying) — dropped the 4th (event-driven earnings IV crush): SPY is an ETF with no earnings events, and early September is a dead zone for single-name earnings generally (Q2 reporters done in August, Q3 doesn't start until mid-October) — no valid catalyst to test against in our live window regardless.
  - [x] 🟩 (a) VRP / Iron Condor selling — sell 4-leg delta-neutral condors (3–7 DTE) when IV (backed out via Black-Scholes from real historical option prices) exceeds 20-day realized vol by a threshold. Implemented in `backtest/strategies/vrp_iron_condor.py`.
  - [ ] 🟥 (b) **Renamed from "Dealer Gamma (GEX) positioning" to "Put-Call Skew Regime"** — confirmed 2026-09-01 that Alpaca's data API (bars and snapshots both) has no open-interest field anywhere, so true GEX (`OI × Gamma × Spot²`) cannot be computed at all, live or historical. Substituted a real, non-fabricated signal instead: put-call IV skew (steepening = hedging demand/fear, flattening = complacency), backed out the same way as the VRP signal, no OI required.
  - [ ] 🟥 (c) Hybrid — VRP core with the skew regime as a filter that skips/resizes trades in unfavorable conditions (FRED net-liquidity overlay dropped for now — no FRED_API_KEY provided yet; can be added later if time permits)
- [x] 🟩 **Step 3: Score & select** — Hybrid VRP+Skew wins on every risk-adjusted metric (win rate, profit factor, max drawdown, Sharpe) across two overlapping lookback windows (30wk and 34wk), while capturing nearly as much total P&L as the more trade-happy skew-only variant with about half the trades. Selected as the live strategy. Full numbers and caveats in `backtest-results.md`.

### Phase 2 — Live Autonomous Agent (bulk of remaining time)
> `[DELEGATING → Codex /run-code]` → `[DELEGATING → Codex /fix-bug]` (if failures) → `[DELEGATING → Codex /review]`

- [x] 🟩 **Step 4: Scaffold the three-layer architecture** — built `agent/` (config, analyst, governor, executor, risk_gates, audit_log, run_agent). Ran a full live cycle end-to-end against the dev paper account on 2026-09-02, including a real (test) 4-leg MLEG order accepted by Alpaca's server, then canceled.
  - [x] 🟩 Analyst layer: Featherless (`deepseek-ai/DeepSeek-V3.2`) regime + bull/bear/risk debate — advisory-only, logged but does not gate execution (see architecture-decisions.md for why)
  - [x] 🟩 Governor layer: deterministic Python — Black-Scholes IV/delta, delta-targeted strike selection (reused from `backtest/`), expiry selection that skips known event dates
  - [x] 🟩 Executor layer: Pydantic-validated `CondorOrderPlan` → Alpaca CLI → atomic MLEG limit order. CLI downloaded as a prebuilt Windows binary (no Go toolchain locally)
- [x] 🟩 **Step 5: Wire risk gates**
  - [x] 🟩 Risk per trade ≤2% of NAV / margin ≤25% of buying power (`risk_gates.size_position`)
  - [x] 🟩 Drawdown circuit breakers (3% halt / 6% kill-switch) computed from Alpaca's own portfolio-history endpoint — no separate state store needed since the account is brand-new
  - [x] 🟩 Wide-spread filter (>5% of mid rejected before a strike is even considered)
  - [x] 🟩 0-DTE auto-liquidation at 3:30 PM ET
- [x] 🟩 **Step 6: Structured audit logging** — `agent/audit_log.py`, one JSON line per decision, also printed to stdout for the GH Actions log
- [x] 🟩 **Step 7: Create the fresh, dedicated Alpaca paper account for judging** — done 2026-09-03
  - [x] 🟩 Starting balance confirmed exactly $100,000 (verified live via `/v2/account`: cash=$100,000, equity=$100,000)
  - [x] 🟩 Account ID: **PA3WNF5ZV8W3** (confirmed distinct from the dev account PA37YZBHY6Q7, options approved level 3, status ACTIVE, created 2026-09-03) — credentials in `.env.local` as `ALPACA_SUBMISSION_*`
- [x] 🟩 **Step 8: GitHub Actions scheduled workflow** — done 2026-09-03, verified live in CI
  - [x] 🟩 `.github/workflows/trading-agent.yml` — cron every 15 min, 13:00-20:00 UTC Mon-Fri (~9 AM-4 PM ET), plus `workflow_dispatch` for manual testing
  - [x] 🟩 Installs Alpaca CLI via `go install` (Linux CI target — local dev used the prebuilt Windows binary, so `agent/config.py` gained an `ALPACA_CLI_PATH` env override for CI to point at its own install)
  - [x] 🟩 Runs `python -m agent.run_agent` with `AGENT_ACCOUNT=submission`
  - [x] 🟩 Commits/pushes `agent/audit_log.jsonl` after each run (`if: always()` - captures failure events too)
  - [x] 🟩 4 GitHub Actions repository secrets set (`ALPACA_SUBMISSION_API_KEY`, `ALPACA_SUBMISSION_SECRET_KEY`, `ALPACA_SUBMISSION_ACCOUNT_ID`, `FEATHERLESS_API_KEY`) by Adwik directly — Claude Code's safety classifier correctly blocked Claude from piping these from `.env.local` into `gh secret set`, even read-only/non-displaying
  - [x] 🟩 **Verified live via `workflow_dispatch`, 2 real bugs caught and fixed before it worked**:
    1. `alpaca --version` (a flag) doesn't exist on this CLI - it uses `version` as a subcommand, per its own README. Wrong flag routed into an authenticated-API code path instead of erroring cleanly, producing a misleading "authentication required" failure.
    2. `backtest/data.py` read the *dev* account's `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` unconditionally at import time; `agent/governor.py` transitively imports that module (via `backtest.strategies.common`) just for the pure `delta_offset_pct` function, but Python still executes the whole module on import. Never surfaced locally because dev credentials always happened to be present in `.env.local` alongside submission ones - CI correctly sets only submission credentials, so it crashed with `KeyError: 'ALPACA_API_KEY'` before ever reaching the account-mode branching logic in `agent/config.py`. Fixed by making the credential read lazy (`_headers()` function, not a module-level dict) in both `backtest/data.py` and `backtest/intraday/data.py` (which imported the same constant directly).
    3. Third run (after both fixes) succeeded end-to-end: circuit breaker check → live signal evaluation → Featherless analyst debate → audit log committed and pushed (`0f1378a`). Scheduled cron now live for real, unattended.

> **2026-09-02, mid-Phase-2 finding:** with only ~2.5 days left, there is exactly ONE weekly SPY cycle left before the deadline. Also discovered SPY has *daily* expiries, and that the obvious "next Friday" (Sep 4) is Non-Farm Payrolls day — switched the live target to **2026-09-03** to avoid trading into a scheduled catalyst our Black-Scholes-based strike selection can't price. See architecture-decisions.md.

> **2026-09-02, strategy detour and reaffirmation:** investigated a real concern (Hybrid fires only ~11x/year — could produce zero trades in our window). Researched and 6-month-backtested 4 industry-standard intraday/0DTE alternatives. All 4 underperformed Hybrid on every risk-adjusted metric (3 of 4 actively lose money over 6 months). Decision reaffirmed: staying with weekly Hybrid VRP+Skew, whose entry gates already tested live-favorable today for real. See intraday-backtest-results.md. No further strategy re-evaluation planned — moving to close out Phase 2/3/4 with the remaining ~2 days.

### Phase 3 — Demo Dashboard (can overlap the tail end of Phase 2)
> `[DELEGATING → Codex /run-code]` → `[DELEGATING → Codex /review]`

- [x] 🟩 Netlify site reading the GitHub Actions job's output — P&L curve, current positions, audit trail — `dashboard/index.html` built 2026-09-03, static site fetching `agent/audit_log.jsonl` directly from the repo (no backend, no client-side API keys), styled to the dataviz skill's validated default palette
- [ ] 🟨 Deploy and confirm the live demo URL — blocked on Adwik logging into a non-QCIN Netlify account (the CLI's default logged-in account is the work/QCIN one, deliberately not used for a personal submission); code is ready to deploy the moment that's done

### Phase 4 — Submission Packaging (last day)
> Claude-managed — content/logistics, not code

- [x] 🟩 One-page write-up: AI logic, risk gates, Alpaca infrastructure implementation — done 2026-09-03, `WRITEUP.md` at repo root
- [x] 🟩 Cover image — done 2026-09-03, `cover.svg` (source) + `cover.png` (1200×630, rendered via headless Chrome — `file://` URLs broke on the spaces in this project's path, served locally over HTTP instead)
- [x] 🟩 Video presentation — done 2026-09-03, `video/presentation.mp4` (2:34, 8 scenes). Wrote `VIDEO_SCRIPT.md` first assuming Claude had no recording capability, but found `ffmpeg` was compiled with `libflite` (real text-to-speech) and used it to synthesize narration per scene, composited over a screenshot of each slide (added a `?slide=N` single-slide capture mode to `slides/index.html` for this), then concatenated - no manual recording needed after all
- [x] 🟩 Slide presentation — done 2026-09-03, `slides/index.html` (8 slides, same visual identity as the cover image) + `slides/deck.pdf` (exported via headless Chrome, verified 8 pages at consistent 16:9)
- [x] 🟩 Final GitHub repo polish (public, README) — done 2026-09-03, `README.md` added (overview, architecture, project structure, run instructions)
- [ ] 🟥 Submit demo URL (Netlify) — not a hard challenge requirement per challenge-and-requirements.md, first thing to cut if time runs out
- [ ] 🟥 Submit the final Alpaca paper trading account ID — account ready (`PA3WNF5ZV8W3`), submission itself not yet filed
- [ ] 🟨 (Optional) up to 5 Build-in-Public social post links (X/LinkedIn, tagging @lablabai + @AlpacaHQ) — 5 drafts written in `SOCIAL_POSTS.md`; Claude does not post on the user's behalf, actual publishing (and the resulting links) is Adwik's to do
- [ ] 🟥 Submit before **Sep 4, 8:30 PM IST**

## Reference repos to review before writing strategy code
- [github.com/alpacahq/options-wheel](https://github.com/alpacahq/options-wheel) — config-driven strategy runner, structured JSON logging pattern
- [github.com/alpacahq/gamma-scalping](https://github.com/alpacahq/gamma-scalping) — reference if the GEX strategy candidate (1b) advances
