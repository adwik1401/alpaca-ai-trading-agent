"""Strategy 1: Systematic 0DTE Delta-Targeted Iron Condor (morning volatility harvest).
Entry ~10:00 AM ET only if the market opened calm (tight opening range, flat VWAP slope).
This is structurally identical to the weekly Hybrid strategy - same condor construction,
same delta targeting, same profit-take/stop-loss logic - just re-timed to intraday."""
from datetime import date, timedelta

from backtest import black_scholes as bs
from backtest import data as daily_data
from . import data, indicators, common

TARGET_DELTA = 0.125  # mid of research's 0.10-0.15 band
WING_WIDTH = 1.0  # research: $1-2 wide for 0DTE (tighter than the weekly $5)
CALM_RANGE_PCT_MAX = 0.005  # 30-min opening range must be < 0.5% of spot
CALM_VWAP_SLOPE_MAX = 0.0002  # flat VWAP slope threshold
PROFIT_TAKE_PCT = 0.5
STOP_LOSS_MULTIPLE = 1.75  # mid of research's 1.5-2.0x


def _sigma_estimate(day: date) -> float:
    """Bootstrap sigma for strike selection from the prior 20 trading days' realized vol -
    we don't have an intraday IV surface without already knowing which strikes to look at,
    so this breaks the circularity the same way the weekly strategy did."""
    start = day - timedelta(days=40)
    bars = daily_data.get_equity_bars("SPY", start.isoformat(), day.isoformat())
    closes = [b["c"] for b in bars if b["t"][:10] < day.isoformat()]
    if len(closes) < 21:
        return 0.10  # reasonable fallback for SPY
    return bs.realized_vol(closes, window=20)


def run(days: list[date], params: dict | None = None) -> dict:
    """`params` optionally overrides any of the 6 module-level constants above (keys:
    target_delta, wing_width, calm_range_pct_max, calm_vwap_slope_max, profit_take_pct,
    stop_loss_multiple) for a single call, without touching the module's own defaults - used by
    `backtest/tuning/` to score candidate parameter sets during the parameter search
    (.claude/plans/0dte-condor-parameter-tuning-plan.md) without mutating this file per attempt.
    Called with no `params` (the normal case, e.g. from run_intraday_backtest.py), behavior is
    unchanged from before this was added."""
    p = params or {}
    target_delta = p.get("target_delta", TARGET_DELTA)
    wing_width = p.get("wing_width", WING_WIDTH)
    calm_range_pct_max = p.get("calm_range_pct_max", CALM_RANGE_PCT_MAX)
    calm_vwap_slope_max = p.get("calm_vwap_slope_max", CALM_VWAP_SLOPE_MAX)
    profit_take_pct = p.get("profit_take_pct", PROFIT_TAKE_PCT)
    stop_loss_multiple = p.get("stop_loss_multiple", STOP_LOSS_MULTIPLE)

    trades, skipped = [], []
    for day in days:
        bars = data.get_intraday_equity_bars(day)
        if len(bars) < 10:
            skipped.append({"day": day.isoformat(), "reason": "insufficient_intraday_bars"})
            continue

        orb = indicators.opening_range(bars)
        if not orb or orb["range_pct"] >= calm_range_pct_max:
            skipped.append({"day": day.isoformat(), "reason": "opening_range_too_wide", "range_pct": orb["range_pct"] if orb else None})
            continue

        vwap = indicators.vwap_series(bars)
        entry_idx = 6  # bar index at/after 10:00 AM (6 x 5min = 30 min after 9:30 open)
        if len(vwap) <= entry_idx:
            skipped.append({"day": day.isoformat(), "reason": "no_10am_bar"})
            continue
        slope = abs(vwap[entry_idx]["vwap"] - vwap[max(0, entry_idx - 3)]["vwap"]) / vwap[entry_idx]["vwap"]
        if slope >= calm_vwap_slope_max:
            skipped.append({"day": day.isoformat(), "reason": "vwap_slope_too_steep", "slope": slope})
            continue

        entry_bar = bars[entry_idx]
        entry_time = entry_bar["t"]
        spot = entry_bar["c"]
        sigma = _sigma_estimate(day)

        built = common.build_condor_legs(day, spot, entry_time, sigma, target_delta, wing_width)
        if not built:
            skipped.append({"day": day.isoformat(), "reason": "no_liquid_contracts"})
            continue

        entry_credit = common.price_condor_at(built["bars"], entry_time)
        if entry_credit is None or entry_credit <= 0:
            skipped.append({"day": day.isoformat(), "reason": "bad_entry_price"})
            continue

        max_loss = wing_width - entry_credit
        contracts = common.size_position(max_loss)
        if contracts < 1:
            skipped.append({"day": day.isoformat(), "reason": "position_size_zero"})
            continue

        all_times = [b["t"] for b in bars]
        spot_by_time = {b["t"]: b["c"] for b in bars}
        trade = common.simulate_credit_spread(
            day, "0dte_iron_condor", built, entry_time, entry_credit, contracts, all_times,
            profit_take_pct, stop_loss_multiple,
            strikes_to_watch=[built["strikes"]["short_put"], built["strikes"]["short_call"]],
            spot_by_time=spot_by_time,
        )
        trades.append(trade.__dict__)

    return {"strategy": "0dte_iron_condor", "trades": trades, "skipped": skipped}
