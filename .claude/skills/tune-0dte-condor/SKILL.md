---
name: tune-0dte-condor
description: Run one agent-driven parameter-search iteration against the 0DTE Iron Condor strategy (backtest/intraday/strategy_1_iron_condor.py), inspired by karpathy/autoresearch's edit-run-check-keep loop. Use when asked to tune, optimize, or improve this strategy's parameters, or when driven repeatedly via /loop to run a bounded search.
---

# Tune 0DTE Iron Condor

One invocation of this skill = one search iteration. This is the "program.md" for an
autoresearch-style loop adapted to this project: instead of an agent editing `train.py` and
checking `val_bpb` on a GPU, you edit one parameter of a real options strategy and check Sharpe
(subject to a drawdown cap) against a real historical backtest. See
`.claude/plans/0dte-condor-parameter-tuning-plan.md` for the full design and the decisions behind
it (target strategy, objective, overfitting guard) before running this for the first time.

**Full plan document**: `.claude/plans/0dte-condor-parameter-tuning-plan.md`
**Search space + bounds**: `backtest/tuning/search_space.py`
**Results ledger**: `backtest/tuning/results/ledger.json`

## Building blocks (do not reimplement these — call them)

- `python -m backtest.tuning.run_eval '<params_json>' train` — scores a candidate parameter set
  against the 84-day train split. Prints a JSON summary including `sharpe`, `max_drawdown_pct`,
  `passes_drawdown_cap`, `eligible` (false if fewer than 15 trades — too few to trust the Sharpe),
  `num_trades`, `return_pct`.
- `python -m backtest.tuning.run_eval '<params_json>' test` — same, but against the held-out
  42-day test split. Only ever call this in Phase 4 (final validation of the winning parameter
  set), never during the search itself — using it mid-search would defeat the point of holding it
  out.
- `python -m backtest.tuning.record '<params_json>' '<param_changed>' '<score_json>' true|false` —
  appends one attempt to the ledger and returns the updated `best` and
  `consecutive_non_improving` streak.
- `backtest/tuning/search_space.py`'s `PARAMS` dict has the baseline value, min, max, and step for
  each of the 6 tunable parameters: `target_delta`, `wing_width`, `calm_range_pct_max`,
  `calm_vwap_slope_max`, `profit_take_pct`, `stop_loss_multiple`.

## One iteration

1. **Read the ledger** (`backtest/tuning/results/ledger.json`). If it doesn't exist yet or
   `attempts` is empty, this is the very first run:
   - Evaluate the baseline params (`search_space.baseline_params()`) on `train` to get a
     reference score, then record it via `record.py` with `param_changed="baseline"` and
     `kept=true` — this seeds `ledger["best"]` so every later attempt has something real to beat.
     Then stop this iteration (report the baseline score) — the first real perturbation happens
     next iteration.
2. **Otherwise, decide what to try next using judgment, not a fixed rotation.** Look at the
   attempt history: which parameters have been tried, in which direction, and what happened.
   Reason about it like a researcher would — if a parameter improved things in one direction,
   consider pushing further in that direction (still respecting its bounds); if a parameter's
   already been tried both directions with no improvement, move on to an untried one; if the
   history is inconclusive, prefer trying a parameter that hasn't been touched yet. This is the
   part of the loop that's genuinely agentic — don't reduce it to "cycle through the list."
3. **Build the candidate**: take `ledger["best"]["params"]` (the current best full parameter set)
   and change exactly ONE field to a new value — the current value for that parameter plus or
   minus its `step` from `search_space.py`, clamped to `[min, max]` via `search_space.clamp()`.
   Changing more than one parameter per iteration makes it impossible to attribute what caused a
   result — don't do it.
4. **Evaluate**: run `run_eval.py` with the candidate params on `train`.
5. **Decide keep or revert**: keep only if ALL of — `score["eligible"]` is true, and
   `score["passes_drawdown_cap"]` is true, and `score["sharpe"] > ledger["best"]["score"]["sharpe"]`.
   Otherwise revert (the candidate is discarded, `ledger["best"]` stays unchanged).
6. **Record**: call `record.py` with the candidate params, which parameter you changed, the score,
   and the keep/revert decision.
7. **Report**: one short status line — parameter changed, direction, new Sharpe vs. previous best,
   kept or reverted, current drawdown, current trade count.
8. **Check the stop condition**: if total recorded attempts (excluding the baseline-seeding one)
   reach 20, OR `consecutive_non_improving` (from `record.py`'s output) reaches 5, the search is
   done — report the final best parameter set and its train-split score, and do not schedule
   another iteration. Otherwise continue to the next iteration.

## After the search ends (Phase 4 — do this once, not per-iteration)

1. Run `run_eval.py` on `test` with the final best parameter set — this is the first and only time
   the test split gets touched.
2. Present train vs. test vs. original-baseline metrics side by side. If test Sharpe is
   substantially worse than train Sharpe, say so plainly — that's the overfitting check actually
   doing its job, not a failure of the tool.
3. Write `.claude/wiki/0dte-condor-tuning-results.md` and append to `.claude/wiki/log.md`.
4. Present the proposed change to `backtest/intraday/strategy_1_iron_condor.py`'s constants as an
   explicit diff and wait for confirmation before applying it — never apply automatically, and
   never touch `agent/config.py` (0DTE Iron Condor is not the live strategy).
