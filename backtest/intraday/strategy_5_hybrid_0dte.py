"""Strategy 5: Hybrid VRP+Skew applied intraday - the SAME validated entry filter concept as
the weekly strategy (IV exceeds realized vol by a threshold, AND put-call skew is not elevated
vs its own recent history), checked once per trading DAY at 10:00 AM ET against that day's
0DTE chain instead of once per WEEK against a ~4-7 DTE chain.

FIX (2026-09-02): the first version of this strategy compared 0DTE IV against daily-close
RV20 and got zero trades in 10/10 days - IV was consistently BELOW RV20 (e.g. 6.6% vs 13.2%),
the opposite of what the filter needs. That's not a real "options are cheap" signal - it's a
regime mismatch: a ~5.5-hour-horizon IV isn't comparable to a 20-*day* realized-vol measure.
Fixed by computing realized vol on the SAME high-frequency (5-min) basis as the option's own
horizon, pooled over the trailing 15 trading days (a rolling buffer built from bars this
backtest already fetches - no extra API calls, and only ever uses PAST days, no look-ahead).
"""
from datetime import date
from collections import deque

from backtest import black_scholes as bs
from backtest.strategies.common import delta_offset_pct
from . import data, indicators, common

TARGET_DELTA = 0.175  # same as the weekly strategy, not Strategy 1's 0.125
WING_WIDTH = 1.0  # intraday scale, per research ($1-2), not the weekly $5
ENTRY_BAR_INDEX = 6  # 10:00 AM ET (30 min after 9:30 open, on 5-min bars)
IV_OVER_RV_RATIO_THRESHOLD = 1.10  # relative, not absolute - a flat +0.02 (weekly's threshold)
# was recalibrated 2026-09-02: intraday vol runs ~6-8% vs the weekly strategy's typical 10-20%,
# so the SAME absolute point-spread is a proportionally much harder bar to clear at this scale.
# Require IV to exceed RV by 10% relatively instead, which scales correctly across regimes.
SKEW_RANK_ELEVATED_THRESHOLD = 65.0  # identical threshold to the weekly strategy
PROFIT_TAKE_PCT = 0.5
STOP_LOSS_MULTIPLE = 1.75
RV_LOOKBACK_DAYS = 15  # trailing days of 5-min returns pooled for the intraday RV estimate
MIN_RETURNS_FOR_RV = 200  # ~2.5 days worth - minimum before trusting the estimate


def _compute_intraday_skew(day: date, spot: float, entry_time: str, sigma_estimate: float) -> float | None:
    T = common.time_to_close_years(entry_time, day)
    offset_pct = delta_offset_pct(sigma_estimate, T, TARGET_DELTA)
    call = common.find_liquid_strike(day, "C", spot * (1 + offset_pct))
    put = common.find_liquid_strike(day, "P", spot * (1 - offset_pct))
    if not call or not put:
        return None
    call_symbol, call_bars = call
    put_symbol, put_bars = put
    call_price = call_bars.get(entry_time, {}).get("c")
    put_price = put_bars.get(entry_time, {}).get("c")
    if not call_price or not put_price:
        return None
    call_strike = float(call_symbol[-8:]) / 1000
    put_strike = float(put_symbol[-8:]) / 1000
    call_iv = bs.implied_vol(call_price, spot, call_strike, T, "C")
    put_iv = bs.implied_vol(put_price, spot, put_strike, T, "P")
    if call_iv is None or put_iv is None:
        return None
    return put_iv - call_iv


def run(days: list[date]) -> dict:
    trades, skipped = [], []
    skew_history = []
    return_buffer = deque(maxlen=RV_LOOKBACK_DAYS * indicators.BARS_PER_TRADING_DAY_5MIN)

    for day in days:
        bars = data.get_intraday_equity_bars(day)
        if len(bars) <= ENTRY_BAR_INDEX:
            skipped.append({"day": day.isoformat(), "reason": "insufficient_intraday_bars"})
            continue

        # Use only PAST days' returns for the RV estimate (no look-ahead), then append
        # today's returns to the buffer for future days to use.
        if len(return_buffer) < MIN_RETURNS_FOR_RV:
            return_buffer.extend(indicators.log_returns_5min(bars))
            skipped.append({"day": day.isoformat(), "reason": "warming_up_rv_buffer", "buffer_size": len(return_buffer)})
            continue
        intraday_rv = indicators.annualize_5min_returns(list(return_buffer))
        return_buffer.extend(indicators.log_returns_5min(bars))

        entry_bar = bars[ENTRY_BAR_INDEX]
        entry_time = entry_bar["t"]
        spot = entry_bar["c"]

        built = common.build_condor_legs(day, spot, entry_time, intraday_rv, TARGET_DELTA, WING_WIDTH)
        if not built:
            skipped.append({"day": day.isoformat(), "reason": "no_liquid_contracts"})
            continue

        sc_price = built["bars"]["short_call"].get(entry_time, {}).get("c")
        T = common.time_to_close_years(entry_time, day)
        iv = bs.implied_vol(sc_price, spot, built["strikes"]["short_call"], T, "C") if sc_price else None

        skew = _compute_intraday_skew(day, spot, entry_time, intraday_rv)
        skew_rank = bs.iv_rank(skew, skew_history) if (skew is not None and skew_history) else 50.0
        if skew is not None:
            skew_history.append(skew)

        vrp_ok = iv is not None and intraday_rv > 0 and (iv / intraday_rv) >= IV_OVER_RV_RATIO_THRESHOLD
        skew_ok = skew is None or skew_rank < SKEW_RANK_ELEVATED_THRESHOLD

        if not (vrp_ok and skew_ok):
            skipped.append({
                "day": day.isoformat(), "reason": "hybrid_filter_failed",
                "iv": iv, "intraday_rv": intraday_rv, "skew": skew, "skew_rank": skew_rank,
                "vrp_ok": vrp_ok, "skew_ok": skew_ok,
            })
            continue

        entry_credit = common.price_condor_at(built["bars"], entry_time)
        if entry_credit is None or entry_credit <= 0:
            skipped.append({"day": day.isoformat(), "reason": "bad_entry_price"})
            continue

        max_loss = WING_WIDTH - entry_credit
        contracts = common.size_position(max_loss)
        if contracts < 1:
            skipped.append({"day": day.isoformat(), "reason": "position_size_zero"})
            continue

        all_times = [b["t"] for b in bars]
        spot_by_time = {b["t"]: b["c"] for b in bars}
        trade = common.simulate_credit_spread(
            day, "hybrid_0dte", built, entry_time, entry_credit, contracts, all_times,
            PROFIT_TAKE_PCT, STOP_LOSS_MULTIPLE,
            strikes_to_watch=[built["strikes"]["short_put"], built["strikes"]["short_call"]],
            spot_by_time=spot_by_time,
        )
        trade_dict = trade.__dict__
        trade_dict["meta"] = {"iv": iv, "intraday_rv": intraday_rv, "skew": skew, "skew_rank": skew_rank}
        trades.append(trade_dict)

    return {"strategy": "hybrid_0dte", "trades": trades, "skipped": skipped}
