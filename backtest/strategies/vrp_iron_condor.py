"""Strategy A: Volatility Risk Premium harvesting via iron condor selling.
Entry signal: IV (from the short strikes, backed out via Black-Scholes) minus 20-day realized
vol is above a threshold - i.e. options are rich relative to how much the underlying is actually
moving. This is the simplest, most defined-risk-by-construction candidate (research: mechanically
easiest to risk-gate, doesn't require a directional call)."""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common

UNDERLYING = "SPY"
WING_WIDTH = 5.0
TARGET_DELTA = 0.175  # midpoint of the 0.15-0.20 research-recommended band
ENTRY_DAYS_BEFORE_EXPIRY = 4  # Monday of expiry week -> ~4 trading days to Friday
IV_MINUS_RV_THRESHOLD = 0.02  # enter only if IV exceeds realized vol by >=2 vol points


def run(lookback_weeks: int = 10) -> dict:
    today = date.today()
    history_start = today - timedelta(weeks=lookback_weeks + 6)  # extra buffer for the 20d RV window
    equity_bars = data.get_equity_bars(UNDERLYING, history_start.isoformat(), today.isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in equity_bars}
    sorted_dates = sorted(closes_by_date.keys())

    fridays = common.fridays_between(today - timedelta(weeks=lookback_weeks), today - timedelta(days=1))

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
        short_offset_pct = common.delta_offset_pct(rv20, T, TARGET_DELTA)

        # Peek at the short strikes' price to back out IV for the entry filter only.
        probe = common.build_condor_legs(
            UNDERLYING, expiry, spot, WING_WIDTH, short_offset_pct, entry_str, (expiry + timedelta(days=1)).isoformat()
        )
        if not probe:
            skipped.append({"expiry": expiry.isoformat(), "reason": "no_liquid_contracts"})
            continue
        sc_price = probe["bars"]["short_call"].get(entry_str, {}).get("c")
        iv = bs.implied_vol(sc_price, spot, probe["strikes"]["short_call"], T, "C") if sc_price else None

        if iv is None or (iv - rv20) < IV_MINUS_RV_THRESHOLD:
            skipped.append({"expiry": expiry.isoformat(), "reason": "iv_rv_spread_below_threshold", "iv": iv, "rv20": rv20})
            continue

        trade = common.simulate_condor_trade(UNDERLYING, entry_date, expiry, spot, WING_WIDTH, short_offset_pct)
        if trade:
            trade_dict = trade.__dict__.copy()
            trade_dict["iv_at_entry"] = iv
            trade_dict["rv20_at_entry"] = rv20
            trades.append(trade_dict)
        else:
            skipped.append({"expiry": expiry.isoformat(), "reason": "trade_construction_failed"})

    return {"strategy": "vrp_iron_condor", "trades": trades, "skipped": skipped}
