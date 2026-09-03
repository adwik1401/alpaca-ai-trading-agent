"""Strategy B: Put-Call Skew Regime (substituted for dealer-GEX positioning - see
architecture-decisions.md for why: Alpaca's data API has no open-interest field anywhere,
so true GEX can't be computed at all).

Signal: put IV minus call IV at symmetric ~0.15-0.20-delta strikes, both backed out via Black-Scholes
from real historical option prices (same technique as the VRP strategy). Elevated skew
(percentile-ranked against its own recent history) means the market is pricing more hedging
demand/downside fear than usual - historically a precursor to vol expansion, so we sit out new
condor entries in that regime rather than sell premium into it. Calm/flat skew regimes are when
we actually take the trade.
"""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common

UNDERLYING = "SPY"
WING_WIDTH = 5.0
TARGET_DELTA = 0.175
ENTRY_DAYS_BEFORE_EXPIRY = 4
SKEW_RANK_ELEVATED_THRESHOLD = 65.0  # skip entries when skew is in the top ~35th percentile


def _compute_skew(entry_str: str, spot: float, expiry: date, sigma_estimate: float) -> float | None:
    data_start = entry_str
    data_end = (expiry + timedelta(days=1)).isoformat()
    T = max((expiry - date.fromisoformat(entry_str)).days, 1) / 365
    offset_pct = common.delta_offset_pct(sigma_estimate, T, TARGET_DELTA)
    call_target = spot * (1 + offset_pct)
    put_target = spot * (1 - offset_pct)

    call = common.find_liquid_strike(UNDERLYING, expiry, "C", call_target, data_start, data_end)
    put = common.find_liquid_strike(UNDERLYING, expiry, "P", put_target, data_start, data_end)
    if not call or not put:
        return None
    call_symbol, call_bars = call
    put_symbol, put_bars = put

    call_price = call_bars.get(entry_str, {}).get("c")
    put_price = put_bars.get(entry_str, {}).get("c")
    if not call_price or not put_price:
        return None

    call_strike = float(call_symbol[-8:]) / 1000
    put_strike = float(put_symbol[-8:]) / 1000
    call_iv = bs.implied_vol(call_price, spot, call_strike, T, "C")
    put_iv = bs.implied_vol(put_price, spot, put_strike, T, "P")
    if call_iv is None or put_iv is None:
        return None
    return put_iv - call_iv


def run(lookback_weeks: int = 10) -> dict:
    today = date.today()
    history_start = today - timedelta(weeks=lookback_weeks + 6)
    equity_bars = data.get_equity_bars(UNDERLYING, history_start.isoformat(), today.isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in equity_bars}
    sorted_dates = sorted(closes_by_date.keys())

    fridays = common.fridays_between(today - timedelta(weeks=lookback_weeks), today - timedelta(days=1))

    skew_history = []
    trades = []
    skipped = []
    for expiry in fridays:
        entry_date = expiry - timedelta(days=ENTRY_DAYS_BEFORE_EXPIRY)
        while entry_date.weekday() >= 5:
            entry_date -= timedelta(days=1)
        entry_str = entry_date.isoformat()
        if entry_str not in closes_by_date:
            continue
        spot = closes_by_date[entry_str]

        past_closes = [closes_by_date[d] for d in sorted_dates if d <= entry_str]
        if len(past_closes) < 21:
            continue
        rv20 = bs.realized_vol(past_closes, window=20)
        T = max((expiry - entry_date).days, 1) / 365
        offset_pct = common.delta_offset_pct(rv20, T, TARGET_DELTA)

        skew = _compute_skew(entry_str, spot, expiry, rv20)
        if skew is None:
            skipped.append({"expiry": expiry.isoformat(), "reason": "skew_not_computable"})
            continue

        skew_rank = bs.iv_rank(skew, skew_history) if skew_history else 50.0
        skew_history.append(skew)

        if skew_rank >= SKEW_RANK_ELEVATED_THRESHOLD:
            skipped.append({"expiry": expiry.isoformat(), "reason": "skew_elevated", "skew": skew, "skew_rank": skew_rank})
            continue

        trade = common.simulate_condor_trade(UNDERLYING, entry_date, expiry, spot, WING_WIDTH, offset_pct)
        if trade:
            trade_dict = trade.__dict__.copy()
            trade_dict["skew_at_entry"] = skew
            trade_dict["skew_rank_at_entry"] = skew_rank
            trades.append(trade_dict)
        else:
            skipped.append({"expiry": expiry.isoformat(), "reason": "trade_construction_failed"})

    return {"strategy": "skew_regime", "trades": trades, "skipped": skipped}
