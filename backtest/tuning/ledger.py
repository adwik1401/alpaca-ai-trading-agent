"""JSON results ledger for the tuning search - one record per attempted iteration, same pattern
as backtest/candidates/results/. Tracks the running best parameter set so each iteration (each a
fresh reasoning step by the agent driving the search) can pick up exactly where the last one left
off without needing to re-derive state from conversation history."""
import json
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent / "results" / "ledger.json"
LEDGER_PATH.parent.mkdir(exist_ok=True)


def load() -> dict:
    if not LEDGER_PATH.exists():
        return {"attempts": [], "best": None}
    return json.loads(LEDGER_PATH.read_text())


def save(ledger: dict) -> None:
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, default=str))


def record_attempt(params: dict, param_changed: str, score: dict, kept: bool) -> dict:
    """Appends one attempt, updates `best` if kept, and persists. Returns the updated ledger."""
    ledger = load()
    ledger["attempts"].append({
        "params": params, "param_changed": param_changed, "score": score, "kept": kept,
    })
    if kept:
        ledger["best"] = {"params": params, "score": score}
    save(ledger)
    return ledger


def consecutive_non_improving() -> int:
    """How many attempts in a row (most recent first) were NOT kept - used as an early-stop
    signal alongside the fixed iteration budget."""
    ledger = load()
    streak = 0
    for attempt in reversed(ledger["attempts"]):
        if attempt["kept"]:
            break
        streak += 1
    return streak
