"""Shared building blocks for the 4 return-competitive candidate strategies (PMCC diagonal, bull
risk reversal, 90/10 call-spread barbell, momentum verticals) researched 2026-09-02 as challengers
to the live Hybrid VRP+Skew strategy. Reuses the weekly engine's contract-discovery primitives
(`find_liquid_strike`) and `Trade` dataclass rather than reimplementing them.

Sign-convention rule (to avoid repeating the 2026-09-02 intraday credit-spread sign bug): every
structure builder here defines `value(d)` as *the net cash you would receive if you executed this
exact set of opening trades (sell what's sold, buy what's bought) at date d's prices*. PnL per
contract is then ALWAYS `value(entry_date) - value(exit_date)`, regardless of whether the position
opened as a net credit or a net debit — this is a bookkeeping identity (cash from opening + cash
from the reverse/closing trades), not a per-structure convention to memorize. Verified against the
existing condor (`entry_credit - exit_value`) and vertical debit spread (`exit_price - entry_debit`)
formulas in strategies/common.py and intraday/common.py - both are special cases of this same rule.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
from scipy.stats import norm

from .. import data, black_scholes as bs
from ..strategies.common import find_liquid_strike, STARTING_NAV, CONTRACT_MULTIPLIER

RISK_FREE_RATE = 0.045


def strike_for_call_delta(spot: float, T: float, sigma: float, target_delta: float, r: float = RISK_FREE_RATE) -> float:
    """Invert Black-Scholes call delta = N(d1) for the strike. Works for both OTM (delta<0.5,
    K>S) and ITM (delta>0.5, K<S) targets - the closed-form inversion used elsewhere in this
    project (`strategies.common.delta_offset_pct`) only handles the OTM case, which is why PMCC's
    deep-ITM long leg (0.80 delta) needs this separate function."""
    if T <= 0 or sigma <= 0:
        return spot
    d1 = norm.ppf(target_delta)
    return float(spot * np.exp(-(d1 * sigma * np.sqrt(T) - (r + 0.5 * sigma**2) * T)))


def strike_for_put_delta(spot: float, T: float, sigma: float, target_delta_abs: float, r: float = RISK_FREE_RATE) -> float:
    """target_delta_abs is the put delta's magnitude (e.g. 0.18 for an 18-delta put, put delta
    itself is -0.18). put delta = N(d1) - 1 => N(d1) = 1 - target_delta_abs."""
    if T <= 0 or sigma <= 0:
        return spot
    d1 = norm.ppf(1 - target_delta_abs)
    return float(spot * np.exp(-(d1 * sigma * np.sqrt(T) - (r + 0.5 * sigma**2) * T)))


def find_strike_with_print_on(underlying: str, expiry: date, right: str, target_strike: float,
                               entry_date_str: str, data_start: str, data_end: str, radius: int = 10) -> tuple[str, dict] | None:
    """Like `find_liquid_strike`, but requires an actual print ON `entry_date_str` specifically -
    not just anywhere in the window. Matters for deep-ITM/long-dated legs (e.g. PMCC's 75-DTE 0.80
    delta long call): those strikes often trade thinly early in their life and only pick up
    volume as expiry nears, so `find_liquid_strike`'s "has some bar somewhere" check can return a
    contract with real data close to its own expiry but nothing on the actual entry date, silently
    breaking position-open accounting (caught 2026-09-02 backtesting the PMCC candidate)."""
    offsets = [0] + [x for i in range(1, radius + 1) for x in (i, -i)]
    for off in offsets:
        strike = round(target_strike) + off
        symbol = data.construct_option_symbol(underlying, expiry, right, strike)
        bars = data.get_option_bars([symbol], data_start, data_end).get(symbol, [])
        if not bars:
            continue
        by_date = _bars_by_date(bars)
        if entry_date_str in by_date:
            return symbol, by_date
    return None


def price_asof(bars_by_date: dict, as_of: str) -> float | None:
    """Close price of the most recent bar at or before `as_of` (standard last-observation-carried-
    forward marking for a thinly-printed instrument) - not an exact-date lookup. This account's
    option data has sparse trade-print coverage outside the most actively-traded near-expiry
    window (confirmed 2026-09-02: a 75-DTE deep-ITM PMCC long leg printed on only ~10 of ~75
    calendar days). An exact `.get(date)` lookup silently returns nothing on the many gap days;
    using that to mean "the position is worth zero" (as an earlier version of this module did when
    closing out a leg on a no-print date) fabricates a loss that never happened in the market."""
    available = [d for d in bars_by_date if d <= as_of]
    if not available:
        return None
    latest = max(available)
    return bars_by_date[latest]["c"]


def nearest_weekday_expiry(target: date) -> date:
    """SPY has daily (M-F) expiries - snap a target calendar date to the nearest trading weekday."""
    d = target
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@dataclass
class CandidateTrade:
    strategy: str
    entry_date: str
    expiry_date: str
    structure: str
    legs: dict
    strikes: dict
    contracts: int
    entry_value: float  # cash received (positive) or paid (negative) opening the position
    exit_date: str = None
    exit_value: float = None
    pnl: float = None
    exit_reason: str = None
    meta: dict = field(default_factory=dict)


def _bars_by_date(bars: list[dict]) -> dict[str, dict]:
    return {b["t"][:10]: b for b in bars}


def build_vertical(underlying: str, expiry: date, right: str, bought_target: float, sold_target: float,
                    data_start: str, data_end: str) -> dict | None:
    """2-leg vertical, same expiry: 'bought' = the leg you buy, 'sold' = the leg you sell.
    Works for both debit verticals (bought nearer/more expensive than sold, e.g. a call debit
    spread) and credit verticals (sold nearer/more expensive, e.g. a put credit spread) - the
    naming is explicit about direction, not implied by moneyness, precisely to avoid the sign
    ambiguity that caused the 2026-09-02 intraday bug."""
    bought = find_liquid_strike(underlying, expiry, right, bought_target, data_start, data_end)
    sold = find_liquid_strike(underlying, expiry, right, sold_target, data_start, data_end)
    if not bought or not sold:
        return None
    bought_symbol, bought_bars = bought
    sold_symbol, sold_bars = sold
    return {
        "legs": {"bought": bought_symbol, "sold": sold_symbol},
        "bars": {"bought": bought_bars, "sold": sold_bars},
        "strikes": {"bought": float(bought_symbol[-8:]) / 1000, "sold": float(sold_symbol[-8:]) / 1000},
    }


def value_vertical(bars_by_leg: dict, d: str) -> float | None:
    """Cash received opening = sold(d) - bought(d) (positive if net credit, negative if net debit).
    Uses `price_asof` (most recent print at-or-before d) per leg rather than an exact-date lookup -
    this account's option data has sparse trade-print coverage away from the final ~2 weeks before
    expiry (confirmed 2026-09-02), so an exact match would silently skip/misvalue many otherwise-
    tradeable days."""
    bought = price_asof(bars_by_leg["bought"], d)
    sold = price_asof(bars_by_leg["sold"], d)
    if bought is None or sold is None:
        return None
    return sold - bought


def build_risk_reversal(underlying: str, expiry: date, spot: float, T: float, sigma: float,
                         put_delta: float, call_delta: float, put_wing: float,
                         data_start: str, data_end: str) -> dict | None:
    """3-leg structure: sell an OTM put (defined-risk via a long put wing below it, same as the
    condor's put side) + buy an OTM call outright (uncapped upside, max loss = premium paid)."""
    short_put_target = strike_for_put_delta(spot, T, sigma, put_delta)
    long_call_target = strike_for_call_delta(spot, T, sigma, call_delta)

    sp = find_liquid_strike(underlying, expiry, "P", short_put_target, data_start, data_end)
    lc = find_liquid_strike(underlying, expiry, "C", long_call_target, data_start, data_end)
    if not sp or not lc:
        return None
    sp_symbol, sp_bars = sp
    lc_symbol, lc_bars = lc

    lp = find_liquid_strike(underlying, expiry, "P", float(sp_symbol[-8:]) / 1000 - put_wing, data_start, data_end, radius=3)
    if not lp:
        return None
    lp_symbol, lp_bars = lp

    return {
        "legs": {"short_put": sp_symbol, "long_put": lp_symbol, "long_call": lc_symbol},
        "bars": {"short_put": sp_bars, "long_put": lp_bars, "long_call": lc_bars},
        "strikes": {
            "short_put": float(sp_symbol[-8:]) / 1000,
            "long_put": float(lp_symbol[-8:]) / 1000,
            "long_call": float(lc_symbol[-8:]) / 1000,
        },
    }


def value_risk_reversal(bars_by_leg: dict, d: str) -> float | None:
    """Cash received opening = short_put(d) - long_put(d) - long_call(d). Uses `price_asof` per
    leg for the same sparse-print reason as `value_vertical` above."""
    sp = price_asof(bars_by_leg["short_put"], d)
    lp = price_asof(bars_by_leg["long_put"], d)
    lc = price_asof(bars_by_leg["long_call"], d)
    if sp is None or lp is None or lc is None:
        return None
    return sp - lp - lc


def simulate_single_shot_trade(strategy: str, structure: str, built: dict, entry_date: date, expiry: date,
                                value_fn, max_loss_per_contract: float, risk_budget_pct: float,
                                profit_take_pct: float, stop_loss_multiple: float | None) -> "CandidateTrade | None":
    """Generic walk-forward simulator for a structure opened once and held to a profit-take/
    stop-loss/expiry exit - covers the barbell call spread, momentum verticals, and risk reversal
    (all single-entry, no rolls). PMCC's diagonal is NOT single-shot (it rolls repeatedly) and uses
    its own ledger-based simulator in pmcc_diagonal.py instead."""
    entry_str = entry_date.isoformat()
    entry_value = value_fn(built["bars"], entry_str)
    if entry_value is None:
        return None
    if max_loss_per_contract <= 0:
        return None

    risk_budget = STARTING_NAV * risk_budget_pct
    contracts = max(1, int(risk_budget / (max_loss_per_contract * CONTRACT_MULTIPLIER)))

    trade = CandidateTrade(
        strategy=strategy, entry_date=entry_str, expiry_date=expiry.isoformat(), structure=structure,
        legs=built["legs"], strikes=built["strikes"], contracts=contracts, entry_value=entry_value,
    )

    d = entry_date + timedelta(days=1)
    last_value = entry_value
    while d <= expiry:
        d_str = d.isoformat()
        val = value_fn(built["bars"], d_str)
        if val is not None:
            last_value = val
            # `captured` is the running per-contract PnL if closed right now (entry_value -
            # exit_value, the same identity every structure's final PnL uses below) - measuring
            # profit-take/stop-loss against max_loss_per_contract (the true risk unit) rather than
            # against entry_value avoids breaking on near-zero-cost entries (e.g. the risk
            # reversal, designed to be opened for ~zero net debit).
            captured = entry_value - val
            if captured >= profit_take_pct * max_loss_per_contract:
                trade.exit_date, trade.exit_value, trade.exit_reason = d_str, val, "profit_take"
                break
            if stop_loss_multiple is not None and -captured >= stop_loss_multiple * max_loss_per_contract:
                trade.exit_date, trade.exit_value, trade.exit_reason = d_str, val, "stop_loss"
                break
        d += timedelta(days=1)

    if trade.exit_date is None:
        trade.exit_date, trade.exit_value, trade.exit_reason = expiry.isoformat(), last_value, "held_to_expiry"

    trade.pnl = (trade.entry_value - trade.exit_value) * CONTRACT_MULTIPLIER * trade.contracts
    return trade


def trend_regime(closes_by_date: dict[str, float], sorted_dates: list[str], as_of: str, sma_window: int = 50) -> str | None:
    """'bull' if spot > SMA(window), 'bear' if below, None if not enough history."""
    past = [closes_by_date[d] for d in sorted_dates if d <= as_of]
    if len(past) < sma_window:
        return None
    sma = sum(past[-sma_window:]) / sma_window
    spot = closes_by_date[as_of]
    return "bull" if spot > sma else "bear"


def cash_yield_accrual(cash_balance: float, days: int, rate: float = RISK_FREE_RATE) -> float:
    return cash_balance * rate * (days / 365)
