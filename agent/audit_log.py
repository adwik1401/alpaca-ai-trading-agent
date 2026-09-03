"""Structured JSON audit logging - every decision the agent makes, appended as one JSON line
per event. This is both a hackathon judging requirement (P&L trace) and the source data for the
Netlify dashboard (Phase 3)."""
import json
from datetime import datetime, timezone

from . import config


def log(event_type: str, payload: dict) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **payload,
    }
    config.AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    print(json.dumps(entry, default=str))
