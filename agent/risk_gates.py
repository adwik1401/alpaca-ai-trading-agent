"""Risk gate layer: circuit breakers and position sizing. Sits between the governor's proposed
plan and the executor - nothing reaches the broker without passing through here first.

Simplification note: "intraday" vs "total" drawdown are both computed from Alpaca's own
portfolio-history endpoint (no separate local state store needed - this is a stateless GitHub
Actions job, so relying on Alpaca as the source of truth for equity history is more robust than
trying to persist our own state file across runs). Given the account is brand new for this
hackathon, the account's full history IS the relevant window - there's no older history to
accidentally include."""
from datetime import datetime, timezone
import zoneinfo

import requests

from . import config

TRADING_BASE = "https://paper-api.alpaca.markets"


def _headers():
    return {"APCA-API-KEY-ID": config.ALPACA_API_KEY, "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY}


def get_account() -> dict:
    r = requests.get(f"{TRADING_BASE}/v2/account", headers=_headers())
    r.raise_for_status()
    return r.json()


def get_drawdown_pct() -> float:
    """Drawdown from this account's peak equity since creation, as a positive fraction."""
    r = requests.get(
        f"{TRADING_BASE}/v2/account/portfolio/history",
        headers=_headers(),
        params={"period": "all", "timeframe": "1D"},
    )
    r.raise_for_status()
    equity = [e for e in r.json().get("equity", []) if e and e > 0]
    if len(equity) < 2:
        return 0.0
    peak = max(equity)
    current = equity[-1]
    return max(0.0, (peak - current) / peak)


def check_circuit_breakers() -> dict:
    """Returns the current risk state. `action` is one of: "normal", "halt_new_entries",
    "kill_switch". Always call this before any new entry, and act on "kill_switch" immediately
    regardless of what else is happening."""
    drawdown = get_drawdown_pct()
    if drawdown >= config.TOTAL_DRAWDOWN_KILL_SWITCH_PCT:
        return {"action": "kill_switch", "drawdown_pct": drawdown}
    if drawdown >= config.INTRADAY_DRAWDOWN_HALT_PCT:
        return {"action": "halt_new_entries", "drawdown_pct": drawdown}
    return {"action": "normal", "drawdown_pct": drawdown}


def size_position(max_loss_per_contract: float, account: dict) -> int:
    """Fractional risk sizing: risk <=2% of NAV per trade, capped separately so margin used
    never exceeds 25% of buying power (whichever binds first, we take the smaller)."""
    nav = float(account["equity"])
    buying_power = float(account.get("options_buying_power") or account["buying_power"])

    risk_budget = nav * config.RISK_PER_TRADE_PCT
    by_risk = int(risk_budget / (max_loss_per_contract * 100)) if max_loss_per_contract > 0 else 0

    margin_budget = buying_power * config.MAX_MARGIN_UTILIZATION_PCT
    by_margin = int(margin_budget / (max_loss_per_contract * 100)) if max_loss_per_contract > 0 else 0

    return max(0, min(by_risk, by_margin))


def is_past_zero_dte_cutoff(expiry_iso: str) -> bool:
    """True if today IS the expiry date and it's at/after 3:30 PM ET - time to force-close any
    remaining short legs rather than risk assignment/after-hours tail risk."""
    et = zoneinfo.ZoneInfo("America/New_York")
    now_et = datetime.now(tz=timezone.utc).astimezone(et)
    if now_et.date().isoformat() != expiry_iso:
        return False
    cutoff = now_et.replace(hour=config.ZERO_DTE_LIQUIDATE_HOUR_ET, minute=config.ZERO_DTE_LIQUIDATE_MINUTE_ET, second=0, microsecond=0)
    return now_et >= cutoff
