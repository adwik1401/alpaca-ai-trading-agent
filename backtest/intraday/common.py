"""Shared 0DTE spread construction, pricing, and trade simulation - used by all 4 intraday
strategy candidates so the actual mechanics (finding real tradeable strikes, walking bars
forward to find an exit) aren't reimplemented 4 times."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backtest import black_scholes as bs
from backtest.strategies.common import delta_offset_pct, STARTING_NAV, RISK_PER_TRADE_PCT, CONTRACT_MULTIPLIER
from . import data

HARD_CLOSE_ET = (15, 30)  # 3:30 PM ET, per research: eliminate gamma explosion / pin risk
ET = ZoneInfo("America/New_York")


@dataclass
class IntradayTrade:
    day: str
    strategy: str
    structure: str  # "credit_spread" or "debit_spread"
    legs: dict
    strikes: dict
    contracts: int
    entry_time: str
    entry_price: float  # positive = credit received, negative = debit paid (per contract)
    exit_time: str = None
    exit_price: float = None
    pnl: float = None
    exit_reason: str = None
    meta: dict = field(default_factory=dict)


def _bars_by_time(bars: list[dict]) -> dict[str, dict]:
    return {b["t"]: b for b in bars}


def time_to_close_years(bar_time_iso: str, day: date) -> float:
    t = datetime.fromisoformat(bar_time_iso.replace("Z", "+00:00")).astimezone(ET)
    close = datetime(day.year, day.month, day.day, 16, 0, tzinfo=ET)
    minutes_to_close = max((close - t).total_seconds() / 60, 1)
    return (minutes_to_close / (6.5 * 60)) / 252


def find_liquid_strike(day: date, right: str, target_strike: float, radius: int = 6) -> tuple[str, dict] | None:
    offsets = [0] + [x for i in range(1, radius + 1) for x in (i, -i)]
    for off in offsets:
        strike = round(target_strike) + off
        symbol = data.construct_0dte_symbol(day, right, strike)
        bars = data.get_intraday_option_bars([symbol], day).get(symbol, [])
        if bars:
            return symbol, _bars_by_time(bars)
    return None


def build_condor_legs(day: date, spot: float, entry_time_iso: str, sigma_estimate: float, target_delta: float, wing_width: float) -> dict | None:
    T = time_to_close_years(entry_time_iso, day)
    offset_pct = delta_offset_pct(sigma_estimate, T, target_delta)
    sc = find_liquid_strike(day, "C", spot * (1 + offset_pct))
    sp = find_liquid_strike(day, "P", spot * (1 - offset_pct))
    if not sc or not sp:
        return None
    sc_symbol, sc_bars = sc
    sp_symbol, sp_bars = sp
    sc_strike = float(sc_symbol[-8:]) / 1000
    sp_strike = float(sp_symbol[-8:]) / 1000

    lc = find_liquid_strike(day, "C", sc_strike + wing_width, radius=3)
    lp = find_liquid_strike(day, "P", sp_strike - wing_width, radius=3)
    if not lc or not lp:
        return None
    lc_symbol, lc_bars = lc
    lp_symbol, lp_bars = lp

    return {
        "legs": {"short_call": sc_symbol, "long_call": lc_symbol, "short_put": sp_symbol, "long_put": lp_symbol},
        "bars": {"short_call": sc_bars, "long_call": lc_bars, "short_put": sp_bars, "long_put": lp_bars},
        "strikes": {"short_call": sc_strike, "long_call": float(lc_symbol[-8:]) / 1000,
                    "short_put": sp_strike, "long_put": float(lp_symbol[-8:]) / 1000},
    }


def build_vertical_spread(day: date, right: str, long_strike_target: float, short_strike_target: float) -> dict | None:
    """2-leg debit spread: buy the near strike, sell the farther OTM strike, same expiry."""
    long_leg = find_liquid_strike(day, right, long_strike_target)
    short_leg = find_liquid_strike(day, right, short_strike_target)
    if not long_leg or not short_leg:
        return None
    long_symbol, long_bars = long_leg
    short_symbol, short_bars = short_leg
    return {
        "legs": {"long": long_symbol, "short": short_symbol},
        "bars": {"long": long_bars, "short": short_bars},
        "strikes": {"long": float(long_symbol[-8:]) / 1000, "short": float(short_symbol[-8:]) / 1000},
    }


def price_condor_at(bars_by_leg: dict[str, dict], t: str) -> float | None:
    try:
        sc = bars_by_leg["short_call"][t]["c"]
        lc = bars_by_leg["long_call"][t]["c"]
        sp = bars_by_leg["short_put"][t]["c"]
        lp = bars_by_leg["long_put"][t]["c"]
    except KeyError:
        return None
    return (sc - lc) + (sp - lp)


def price_vertical_at(bars_by_leg: dict[str, dict], t: str) -> float | None:
    try:
        long_price = bars_by_leg["long"][t]["c"]
        short_price = bars_by_leg["short"][t]["c"]
    except KeyError:
        return None
    return long_price - short_price  # positive = net debit (what the spread is worth)


def size_position(max_loss_per_contract: float) -> int:
    if max_loss_per_contract <= 0:
        return 0
    risk_budget = STARTING_NAV * RISK_PER_TRADE_PCT
    return max(0, int(risk_budget / (max_loss_per_contract * CONTRACT_MULTIPLIER)))


def is_past_hard_close(t: str) -> bool:
    dt = datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(ET)
    return (dt.hour, dt.minute) >= HARD_CLOSE_ET


def simulate_credit_spread(day: date, strategy: str, structure_legs: dict, entry_time: str, entry_credit: float,
                            contracts: int, all_times: list[str], profit_take_pct: float, stop_loss_multiple: float,
                            strikes_to_watch: list[float] = None, spot_by_time: dict = None) -> IntradayTrade:
    """Walk forward bar-by-bar for a credit spread (condor or single vertical), applying:
    profit-take, stop-loss, hard time-stop, and (if strikes_to_watch given) a strike-breach exit."""
    trade = IntradayTrade(
        day=day.isoformat(), strategy=strategy, structure="credit_spread",
        legs=structure_legs["legs"], strikes=structure_legs["strikes"], contracts=contracts,
        entry_time=entry_time, entry_price=entry_credit,
    )
    pricer = price_condor_at if len(structure_legs["legs"]) == 4 else price_vertical_at
    last_value = entry_credit
    for t in all_times:
        if t <= entry_time:
            continue
        val = pricer(structure_legs["bars"], t)
        if val is None:
            continue
        last_value = val
        captured = entry_credit - val
        if captured >= profit_take_pct * entry_credit:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "profit_take"
            break
        loss = val - entry_credit
        if loss >= stop_loss_multiple * entry_credit:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "stop_loss"
            break
        if strikes_to_watch and spot_by_time and t in spot_by_time:
            spot = spot_by_time[t]
            if spot <= strikes_to_watch[0] or spot >= strikes_to_watch[1]:
                trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "strike_breach"
                break
        if is_past_hard_close(t):
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "hard_time_stop"
            break

    if trade.exit_time is None:
        trade.exit_time, trade.exit_price, trade.exit_reason = all_times[-1], last_value, "eod_forced_close"

    trade.pnl = (entry_credit - trade.exit_price) * 100 * contracts
    return trade


def simulate_debit_spread(day: date, strategy: str, structure_legs: dict, entry_time: str, entry_debit: float,
                           contracts: int, all_times: list[str], profit_take_pct: float, stop_loss_pct: float) -> IntradayTrade:
    trade = IntradayTrade(
        day=day.isoformat(), strategy=strategy, structure="debit_spread",
        legs=structure_legs["legs"], strikes=structure_legs["strikes"], contracts=contracts,
        entry_time=entry_time, entry_price=entry_debit,
    )
    last_value = entry_debit
    for t in all_times:
        if t <= entry_time:
            continue
        val = price_vertical_at(structure_legs["bars"], t)
        if val is None:
            continue
        last_value = val
        roi = (val - entry_debit) / entry_debit if entry_debit > 0 else 0
        if roi >= profit_take_pct:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "profit_take"
            break
        if roi <= -stop_loss_pct:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "stop_loss"
            break
        if is_past_hard_close(t):
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "hard_time_stop"
            break

    if trade.exit_time is None:
        trade.exit_time, trade.exit_price, trade.exit_reason = all_times[-1], last_value, "eod_forced_close"

    trade.pnl = (trade.exit_price - entry_debit) * 100 * contracts
    return trade
