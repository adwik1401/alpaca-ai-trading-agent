"""CLI wrapper to append one attempt to the tuning ledger.

Usage:
  python -m backtest.tuning.record '<params_json>' '<param_changed>' '<score_json>' true|false
"""
import sys
import json

from . import ledger


def main():
    params = json.loads(sys.argv[1])
    param_changed = sys.argv[2]
    score = json.loads(sys.argv[3])
    kept = sys.argv[4].lower() == "true"

    updated = ledger.record_attempt(params, param_changed, score, kept)
    print(json.dumps({
        "num_attempts": len(updated["attempts"]),
        "best": updated["best"],
        "consecutive_non_improving": ledger.consecutive_non_improving(),
    }, indent=2))


if __name__ == "__main__":
    main()
