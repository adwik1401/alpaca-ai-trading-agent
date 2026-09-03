"""Agent configuration: which Alpaca account to trade, strategy parameters, and risk gates.
Reuses the exact strategy the backtest selected (Hybrid VRP+Skew) - see
.claude/wiki/backtest-results.md for why."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")

# AGENT_ACCOUNT=dev (default, safe) or "submission" (the real judged account).
# Defaults to dev so the agent never accidentally trades the judged account
# without an explicit opt-in.
ACCOUNT_MODE = os.environ.get("AGENT_ACCOUNT", "dev")

if ACCOUNT_MODE == "submission":
    ALPACA_API_KEY = os.environ["ALPACA_SUBMISSION_API_KEY"]
    ALPACA_SECRET_KEY = os.environ["ALPACA_SUBMISSION_SECRET_KEY"]
    ALPACA_ACCOUNT_ID = os.environ.get("ALPACA_SUBMISSION_ACCOUNT_ID", "")
else:
    ALPACA_API_KEY = os.environ["ALPACA_API_KEY"]
    ALPACA_SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]
    ALPACA_ACCOUNT_ID = ""

FEATHERLESS_API_KEY = os.environ["FEATHERLESS_API_KEY"]
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
MODEL_FAST = "meta-llama/Meta-Llama-3.1-8B-Instruct"
MODEL_REASONING = "deepseek-ai/DeepSeek-V3.2"

# CI (GitHub Actions, Linux) installs the CLI via `go install` rather than using the local
# Windows binary in tools/ - ALPACA_CLI_PATH lets the workflow point at that install location
# instead. Local dev is unaffected since this env var is never set outside CI.
ALPACA_CLI_PATH = os.environ.get("ALPACA_CLI_PATH") or str(ROOT / "tools" / ("alpaca.exe" if os.name == "nt" else "alpaca"))

UNDERLYING = "SPY"
WING_WIDTH = 5.0
TARGET_DELTA = 0.175
IV_MINUS_RV_THRESHOLD = 0.02
SKEW_RANK_ELEVATED_THRESHOLD = 65.0

# Expiries to skip entirely - our delta-targeted strike selection is Black-Scholes-based
# (continuous diffusion) and cannot price jump/gap risk from a scheduled binary event.
# 2026-09-04 is Non-Farm Payrolls day (first Friday of the month) - decided 2026-09-02 to
# target 2026-09-03 instead. See architecture-decisions.md.
AVOID_EXPIRY_DATES = ["2026-09-04"]

# Risk gates (defaults from research, see architecture-decisions.md)
RISK_PER_TRADE_PCT = 0.02
MAX_MARGIN_UTILIZATION_PCT = 0.25
INTRADAY_DRAWDOWN_HALT_PCT = 0.03
TOTAL_DRAWDOWN_KILL_SWITCH_PCT = 0.06
MAX_SPREAD_PCT_OF_MID = 0.05
PROFIT_TAKE_PCT = 0.5
STOP_LOSS_MULTIPLE = 2.0
ZERO_DTE_LIQUIDATE_HOUR_ET = 15
ZERO_DTE_LIQUIDATE_MINUTE_ET = 30

AUDIT_LOG_PATH = ROOT / "agent" / "audit_log.jsonl"
STATE_PATH = ROOT / "agent" / "state.json"
