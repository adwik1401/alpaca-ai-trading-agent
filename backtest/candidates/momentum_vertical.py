"""Candidate 4: Momentum-timed directional verticals. Weekly trend gate (50-day SMA on SPY closes,
a real-data proxy for the research's EMA/VIX regime filter - consistent with this project's existing
practice of substituting a computable real signal for one Alpaca can't supply, e.g. skew-for-GEX in
skew_regime.py). Bull regime -> call debit spread; bear regime -> put debit spread; flat/undetermined
-> skip. Research source: Antigravity CLI, 2026-09-02 (ranked #4 of 4 - flagged for "whipsaw tax"
during sideways chop)."""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common

UNDERLYING = "SPY"
ENTRY_INTERVAL_DAYS = 7
# DEVIATION FROM RESEARCH (2026-09-02): research proposed 30-45 DTE; this account's SPY options
# data has essentially no trade prints earlier than ~14 days before a contract's own expiry
# (confirmed by direct testing - see pmcc_diagonal.py's module docstring). 12 DTE keeps a 2-day
# safety margin inside that window.
TARGET_DTE = 12
BOUGHT_DELTA = 0.50
SOLD_DELTA = 0.25
RISK_PER_TRADE_PCT = 0.02  # consistent with the existing weekly condor's defined-risk sizing
PROFIT_TAKE_ROI = 1.0  # exit at +100% of debit paid


def run(lookback_weeks: int = 26) -> dict:
    today = date.today()
    history_start = today - timedelta(weeks=lookback_weeks + 12)  # extra buffer for the 50-day SMA
    equity_bars = data.get_equity_bars(UNDERLYING, history_start.isoformat(), (today + timedelta(weeks=8)).isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in equity_bars}
    sorted_dates = sorted(closes_by_date.keys())

    lookback_start = today - timedelta(weeks=lookback_weeks)
    entry_dates = []
    d = lookback_start
    while d <= today - timedelta(days=TARGET_DTE + 3):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        entry_dates.append(d)
        d += timedelta(days=ENTRY_INTERVAL_DAYS)

    trades, skipped = [], []
    for entry_date in entry_dates:
        entry_str = entry_date.isoformat()
        if entry_str not in closes_by_date:
            skipped.append({"entry_date": entry_str, "reason": "no_equity_bar"})
            continue
        spot = closes_by_date[entry_str]

        regime = common.trend_regime(closes_by_date, sorted_dates, entry_str, sma_window=50)
        if regime is None:
            skipped.append({"entry_date": entry_str, "reason": "insufficient_sma_history"})
            continue

        past_closes = [closes_by_date[dd] for dd in sorted_dates if dd <= entry_str]
        if len(past_closes) < 21:
            skipped.append({"entry_date": entry_str, "reason": "insufficient_rv_history"})
            continue
        sigma = bs.realized_vol(past_closes, window=20)

        expiry = common.nearest_weekday_expiry(entry_date + timedelta(days=TARGET_DTE))
        T = max((expiry - entry_date).days, 1) / 365
        data_start = (entry_date - timedelta(days=5)).isoformat()
        data_end = (expiry + timedelta(days=1)).isoformat()

        if regime == "bull":
            right = "C"
            bought_target = common.strike_for_call_delta(spot, T, sigma, BOUGHT_DELTA)
            sold_target = common.strike_for_call_delta(spot, T, sigma, SOLD_DELTA)
        else:
            right = "P"
            bought_target = common.strike_for_put_delta(spot, T, sigma, BOUGHT_DELTA)
            sold_target = common.strike_for_put_delta(spot, T, sigma, SOLD_DELTA)

        built = common.build_vertical(UNDERLYING, expiry, right, bought_target, sold_target, data_start, data_end)
        if not built:
            skipped.append({"entry_date": entry_str, "reason": "no_liquid_contracts", "regime": regime})
            continue

        entry_value = common.value_vertical(built["bars"], entry_str)
        if entry_value is None or entry_value >= 0:
            skipped.append({"entry_date": entry_str, "reason": "not_a_net_debit", "entry_value": entry_value})
            continue
        max_loss_per_contract = -entry_value

        trade = common.simulate_single_shot_trade(
            strategy="momentum_vertical", structure="debit_vertical", built=built,
            entry_date=entry_date, expiry=expiry, value_fn=common.value_vertical,
            max_loss_per_contract=max_loss_per_contract, risk_budget_pct=RISK_PER_TRADE_PCT,
            profit_take_pct=PROFIT_TAKE_ROI, stop_loss_multiple=None,
        )
        if trade:
            trade.meta = {"spot_at_entry": spot, "sigma_at_entry": sigma, "regime": regime}
            trades.append(trade.__dict__)
        else:
            skipped.append({"entry_date": entry_str, "reason": "trade_construction_failed", "regime": regime})

    return {"strategy": "momentum_vertical", "trades": trades, "skipped": skipped}
