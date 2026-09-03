"""Analyst layer: the only place an LLM touches this pipeline. It classifies market regime and
runs a bull/bear/risk debate for the audit trail - it never computes Greeks, never picks a
strike, and never sets a price (research finding: LLMs have +-15-40% error rates on option math
done in token space).

IMPORTANT - advisory only, not a gate: an earlier live test (2026-09-02) had this layer
recommend "abstain" while citing Labor Day holiday-thinned liquidity as a risk - except Labor
Day 2026 (Aug 31) had already passed by the time of that test. The underlying instinct (short
DTE carries more gamma risk) was reasonable; the specific justification was fabricated. Given
that demonstrated failure mode, this layer's `recommendation`/`abstain_reason` is recorded in
full in the audit log for transparency and judging value, but it does NOT block or gate order
execution - only the deterministic VRP+skew signal (governor.py) and the circuit breakers
(risk_gates.py) get to decide go/no-go. This keeps the "zero-trust" pipeline honest: the LLM
narrates, it does not have execution authority."""
import json
from datetime import date

import requests

from . import config

SYSTEM_PROMPT = """You are the risk-debate layer of an autonomous options trading agent. You do \
NOT compute option prices, Greeks, or strikes - a deterministic engine already did that and \
will act on its own signal regardless of your opinion on the numbers. Your only job: given the \
market snapshot below, run a brief bull case, bear case, and a named-risk check, then decide \
whether the agent's timing is imprudent for a reason that would not show up in IV/RV/skew \
numbers alone (e.g. a specific known market event). Reply with ONLY a JSON object, no prose \
outside it, matching exactly this schema:
{"market_regime": "one short label, e.g. HIGH_IV_RANGEBOUND | BREAKOUT_EVENT | VOLATILITY_EXPANSION | CALM_DRIFT",
 "bull_thesis": "1-2 sentences",
 "bear_thesis": "1-2 sentences",
 "risk_note": "1-2 sentences naming any concrete risk, or 'none identified'",
 "recommendation": "proceed" or "abstain",
 "abstain_reason": "empty string if recommendation is proceed, else why"}"""


def _call_featherless(model: str, user_prompt: str) -> str:
    r = requests.post(
        f"{config.FEATHERLESS_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.FEATHERLESS_API_KEY}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        },
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def run_debate(signal: dict) -> dict:
    """signal is the dict returned by governor.build_live_condor_signal(). Returns the parsed
    debate JSON, or a safe abstain-on-failure default if the LLM call or parsing fails - a
    broken analyst call must never silently become an unreviewed trade."""
    days_to_expiry = (date.fromisoformat(signal["expiry"]) - date.today()).days if signal.get("expiry") else None
    user_prompt = (
        f"Today's date: {date.today().isoformat()}\n"
        f"Underlying: {config.UNDERLYING}\n"
        f"Spot: {signal.get('spot')}\n"
        f"Expiry: {signal.get('expiry')} ({days_to_expiry} days from today - this is a short-dated weekly option, not a long-dated one)\n"
        f"Realized vol (20d): {signal.get('rv20')}\n"
        f"Implied vol (short call): {signal.get('iv')}\n"
        f"Put-call skew: {signal.get('skew')}\n"
        f"Proposed structure: iron condor, net credit {signal.get('net_credit')}\n"
        f"Quantitative gates: VRP_ok={signal.get('vrp_ok')}, skew_ok={signal.get('skew_ok')}\n"
    )
    try:
        raw = _call_featherless(config.MODEL_REASONING, user_prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        assert parsed.get("recommendation") in ("proceed", "abstain")
        return parsed
    except Exception as e:
        return {
            "market_regime": "UNKNOWN",
            "bull_thesis": "",
            "bear_thesis": "",
            "risk_note": f"analyst call failed: {e}",
            "recommendation": "abstain",
            "abstain_reason": f"analyst_error: {e}",
        }
