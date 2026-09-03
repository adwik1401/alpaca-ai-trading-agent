"""Strategy C: Hybrid - VRP core entry signal (IV-RV spread) AND the skew regime filter both
need to be favorable before a trade is taken. FRED net-liquidity overlay from the original
research is left out for now (no FRED_API_KEY provided) - can be layered in later without
changing this structure if time permits."""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common
from .skew_regime import _compute_skew, SKEW_RANK_ELEVATED_THRESHOLD

UNDERLYING = "SPY"
WING_WIDTH = 5.0
TARGET_DELTA = 0.175
ENTRY_DAYS_BEFORE_EXPIRY = 4
IV_MINUS_RV_THRESHOLD = 0.02


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

        probe = common.build_condor_legs(
            UNDERLYING, expiry, spot, WING_WIDTH, offset_pct, entry_str, (expiry + timedelta(days=1)).isoformat()
        )
        if not probe:
            skipped.append({"expiry": expiry.isoformat(), "reason": "no_liquid_contracts"})
            continue
        sc_price = probe["bars"]["short_call"].get(entry_str, {}).get("c")
        iv = bs.implied_vol(sc_price, spot, probe["strikes"]["short_call"], T, "C") if sc_price else None

        skew = _compute_skew(entry_str, spot, expiry, rv20)
        skew_rank = bs.iv_rank(skew, skew_history) if (skew is not None and skew_history) else 50.0
        if skew is not None:
            skew_history.append(skew)

        vrp_ok = iv is not None and (iv - rv20) >= IV_MINUS_RV_THRESHOLD
        skew_ok = skew is None or skew_rank < SKEW_RANK_ELEVATED_THRESHOLD  # unknown skew doesn't block, just doesn't help

        if not (vrp_ok and skew_ok):
            skipped.append({
                "expiry": expiry.isoformat(), "reason": "hybrid_filter_failed",
                "iv": iv, "rv20": rv20, "skew": skew, "skew_rank": skew_rank,
                "vrp_ok": vrp_ok, "skew_ok": skew_ok,
            })
            continue

        trade = common.simulate_condor_trade(UNDERLYING, entry_date, expiry, spot, WING_WIDTH, offset_pct)
        if trade:
            trade_dict = trade.__dict__.copy()
            trade_dict.update({"iv_at_entry": iv, "rv20_at_entry": rv20, "skew_at_entry": skew, "skew_rank_at_entry": skew_rank})
            trades.append(trade_dict)
        else:
            skipped.append({"expiry": expiry.isoformat(), "reason": "trade_construction_failed"})

    return {"strategy": "hybrid_vrp_skew", "trades": trades, "skipped": skipped}
