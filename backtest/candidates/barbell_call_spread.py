"""Candidate 3: "90/10" convex growth barbell. 90% of NAV parked as cash collateral (earns the
risk-free rate); the remaining ~10% risk budget is split into staggered call debit spread tranches
entered every 2 weeks, each independently defined-risk (max loss = debit paid). Research source:
Antigravity CLI, 2026-09-02 (trading-strategy replacement research, ranked #3 of 4)."""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common

UNDERLYING = "SPY"
ENTRY_INTERVAL_DAYS = 7
# DEVIATION FROM RESEARCH (2026-09-02): the research proposed 30-45 DTE entries, but direct
# testing found this account's SPY options data has essentially no trade prints earlier than ~14
# calendar days before a contract's own expiry, regardless of strike/moneyness (confirmed across
# multiple expiries - see backtest/candidates/pmcc_diagonal.py's module docstring and the
# 2026-09-02 session notes). 12 DTE keeps a 2-day safety margin inside that window rather than
# sitting exactly on the boundary. This shortens the holding period materially from the original
# "90/10 barbell" concept - flagged honestly rather than silently backtesting on data that doesn't
# exist.
TARGET_DTE = 12
BOUGHT_DELTA = 0.55
SOLD_DELTA = 0.25
TRANCHE_RISK_PCT = 0.025  # ~2 concurrent weekly tranches given the shorter hold ~= 5% NAV active
PROFIT_TAKE_ROI = 1.5  # exit at +150% of debit paid, per the research's example math


def run(lookback_weeks: int = 26) -> dict:
    today = date.today()
    history_start = today - timedelta(weeks=lookback_weeks + 6)
    equity_bars = data.get_equity_bars(UNDERLYING, history_start.isoformat(), (today + timedelta(weeks=8)).isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in equity_bars}
    sorted_dates = sorted(closes_by_date.keys())

    lookback_start = today - timedelta(weeks=lookback_weeks)
    entry_dates = []
    d = lookback_start
    while d <= today - timedelta(days=TARGET_DTE + 3):  # leave room for the position to actually expire within available data
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

        past_closes = [closes_by_date[dd] for dd in sorted_dates if dd <= entry_str]
        if len(past_closes) < 21:
            skipped.append({"entry_date": entry_str, "reason": "insufficient_rv_history"})
            continue
        sigma = bs.realized_vol(past_closes, window=20)

        expiry = common.nearest_weekday_expiry(entry_date + timedelta(days=TARGET_DTE))
        T = max((expiry - entry_date).days, 1) / 365

        bought_target = common.strike_for_call_delta(spot, T, sigma, BOUGHT_DELTA)
        sold_target = common.strike_for_call_delta(spot, T, sigma, SOLD_DELTA)
        # Small lookback buffer before entry (not just entry_str onward) so `price_asof` can find
        # a real print even if the actual print-coverage floor lands a day or two off the ~14-DTE
        # estimate for this particular contract.
        data_start = (entry_date - timedelta(days=5)).isoformat()
        data_end = (expiry + timedelta(days=1)).isoformat()

        built = common.build_vertical(UNDERLYING, expiry, "C", bought_target, sold_target, data_start, data_end)
        if not built:
            skipped.append({"entry_date": entry_str, "reason": "no_liquid_contracts"})
            continue

        entry_value = common.value_vertical(built["bars"], entry_str)
        if entry_value is None or entry_value >= 0:
            skipped.append({"entry_date": entry_str, "reason": "not_a_net_debit", "entry_value": entry_value})
            continue
        max_loss_per_contract = -entry_value  # debit spread: max loss = debit paid

        trade = common.simulate_single_shot_trade(
            strategy="barbell_call_spread", structure="debit_vertical", built=built,
            entry_date=entry_date, expiry=expiry, value_fn=common.value_vertical,
            max_loss_per_contract=max_loss_per_contract, risk_budget_pct=TRANCHE_RISK_PCT,
            profit_take_pct=PROFIT_TAKE_ROI, stop_loss_multiple=None,
        )
        if trade:
            trade.meta = {"spot_at_entry": spot, "sigma_at_entry": sigma}
            trades.append(trade.__dict__)
        else:
            skipped.append({"entry_date": entry_str, "reason": "trade_construction_failed"})

    return {"strategy": "barbell_call_spread", "trades": trades, "skipped": skipped}
