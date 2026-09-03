"""Shared options-spread backtest engine. Each strategy supplies an entry-decision signal and a
structure builder (condor vs. directional debit spread); this module handles contract discovery,
position sizing under the risk gates, and daily mark-to-market."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from scipy.stats import norm

from .. import data, black_scholes as bs

STARTING_NAV = 100_000.0
RISK_PER_TRADE_PCT = 0.02  # upper bound from research (1.5-2% of NAV)
CONTRACT_MULTIPLIER = 100


def delta_offset_pct(sigma_estimate: float, T_years: float, target_delta: float = 0.175) -> float:
    """Approximate %-OTM offset that targets a given call delta, given a vol estimate and time
    to expiry. Short-dated options need a much tighter offset than long-dated ones for the same
    delta - a fixed % offset (e.g. a blanket 5%) badly overshoots on a 3-7 DTE option and ends up
    selling near-worthless, near-zero-premium strikes instead of the intended ~0.15-0.20 delta."""
    d1_target = -norm.ppf(target_delta)  # positive number; OTM call has K > S so d1 is negative
    return max(0.002, d1_target * sigma_estimate * (T_years ** 0.5))


@dataclass
class Trade:
    entry_date: str
    expiry_date: str
    structure: str  # "iron_condor" or "debit_spread"
    legs: dict  # leg name -> option symbol
    strikes: dict
    contracts: int
    entry_credit_or_debit: float  # positive = credit received, negative = debit paid, per contract
    exit_date: str = None
    exit_value: float = None  # per-contract value paid/received to close
    pnl: float = None
    exit_reason: str = None
    daily_marks: list = field(default_factory=list)  # [(date, nav_delta)]


def fridays_between(start: date, end: date) -> list[date]:
    d = start
    while d.weekday() != 4:  # Friday = 4
        d += timedelta(days=1)
    fridays = []
    while d <= end:
        fridays.append(d)
        d += timedelta(days=7)
    return fridays


def _bars_by_date(bars: list[dict]) -> dict[str, dict]:
    return {b["t"][:10]: b for b in bars}


def find_liquid_strike(underlying: str, expiry: date, right: str, target_strike: float, data_start: str, data_end: str, radius: int = 6) -> tuple[str, dict] | None:
    """Search integer strikes near target for one with real traded bars in the window."""
    offsets = [0] + [x for i in range(1, radius + 1) for x in (i, -i)]
    for off in offsets:
        strike = round(target_strike) + off
        symbol = data.construct_option_symbol(underlying, expiry, right, strike)
        bars = data.get_option_bars([symbol], data_start, data_end).get(symbol, [])
        if bars:
            return symbol, _bars_by_date(bars)
    return None


def build_condor_legs(underlying: str, expiry: date, spot: float, wing_width: float, short_offset_pct: float, data_start: str, data_end: str) -> dict | None:
    """4-leg delta-neutral iron condor via strike-offset proxy for ~0.15-0.20 delta (short-dated
    SPY options at 3-7 DTE and ~5% OTM are a reasonable approximation of that delta band)."""
    short_call_target = spot * (1 + short_offset_pct)
    short_put_target = spot * (1 - short_offset_pct)

    sc = find_liquid_strike(underlying, expiry, "C", short_call_target, data_start, data_end)
    sp = find_liquid_strike(underlying, expiry, "P", short_put_target, data_start, data_end)
    if not sc or not sp:
        return None
    sc_symbol, sc_bars = sc
    sp_symbol, sp_bars = sp

    lc = find_liquid_strike(underlying, expiry, "C", float(sc_symbol[-8:]) / 1000 + wing_width, data_start, data_end, radius=3)
    lp = find_liquid_strike(underlying, expiry, "P", float(sp_symbol[-8:]) / 1000 - wing_width, data_start, data_end, radius=3)
    if not lc or not lp:
        return None
    lc_symbol, lc_bars = lc
    lp_symbol, lp_bars = lp

    return {
        "legs": {"short_call": sc_symbol, "long_call": lc_symbol, "short_put": sp_symbol, "long_put": lp_symbol},
        "bars": {"short_call": sc_bars, "long_call": lc_bars, "short_put": sp_bars, "long_put": lp_bars},
        "strikes": {
            "short_call": float(sc_symbol[-8:]) / 1000,
            "long_call": float(lc_symbol[-8:]) / 1000,
            "short_put": float(sp_symbol[-8:]) / 1000,
            "long_put": float(lp_symbol[-8:]) / 1000,
        },
    }


def price_condor(bars_by_leg: dict[str, dict], d: str) -> float | None:
    """Net credit value of the condor on date d (short legs - long legs), using close price.
    Returns None if any leg is missing a print that day (treated as untradeable, no data day)."""
    try:
        sc = bars_by_leg["short_call"][d]["c"]
        lc = bars_by_leg["long_call"][d]["c"]
        sp = bars_by_leg["short_put"][d]["c"]
        lp = bars_by_leg["long_put"][d]["c"]
    except KeyError:
        return None
    return (sc - lc) + (sp - lp)


def simulate_condor_trade(underlying: str, entry_date: date, expiry: date, spot_entry: float, wing_width: float, short_offset_pct: float, max_loss_cap_multiple: float = 2.0) -> Trade | None:
    data_start = entry_date.isoformat()
    data_end = (expiry + timedelta(days=1)).isoformat()

    built = build_condor_legs(underlying, expiry, spot_entry, wing_width, short_offset_pct, data_start, data_end)
    if not built:
        return None

    entry_str = entry_date.isoformat()
    entry_credit = price_condor(built["bars"], entry_str)
    if entry_credit is None or entry_credit <= 0:
        return None

    max_loss_per_contract = wing_width - entry_credit
    if max_loss_per_contract <= 0:
        return None  # bad fill / no real edge

    risk_budget = STARTING_NAV * RISK_PER_TRADE_PCT
    contracts = max(1, int(risk_budget / (max_loss_per_contract * CONTRACT_MULTIPLIER)))

    trade = Trade(
        entry_date=entry_str,
        expiry_date=expiry.isoformat(),
        structure="iron_condor",
        legs=built["legs"],
        strikes=built["strikes"],
        contracts=contracts,
        entry_credit_or_debit=entry_credit,
    )

    # Walk forward day by day for exit rules: 50% profit take, or loss > 2x credit (risk gate).
    d = entry_date + timedelta(days=1)
    last_value = entry_credit
    while d <= expiry:
        d_str = d.isoformat()
        val = price_condor(built["bars"], d_str)
        if val is not None:
            last_value = val
            profit_captured = entry_credit - val
            if profit_captured >= 0.5 * entry_credit:
                trade.exit_date, trade.exit_value, trade.exit_reason = d_str, val, "profit_take_50pct"
                break
            loss = val - entry_credit
            if loss >= max_loss_cap_multiple * entry_credit:
                trade.exit_date, trade.exit_value, trade.exit_reason = d_str, val, "stop_loss_2x_credit"
                break
        d += timedelta(days=1)

    if trade.exit_date is None:
        trade.exit_date, trade.exit_value, trade.exit_reason = expiry.isoformat(), last_value, "held_to_expiry"

    trade.pnl = (entry_credit - trade.exit_value) * CONTRACT_MULTIPLIER * trade.contracts
    return trade
