"""Candidate 2: Defined-risk bull risk reversal (skew-monetized synthetic long). Sell an OTM put
(protected by a long put wing, same defined-risk mechanic as the condor's put side) to fund buying
an OTM call outright - structural put-over-call IV skew means the put side frequently funds most or
all of the call, for near-zero net cost, uncapped upside. Gated to bull/neutral regime (50-day SMA)
per the research, since the short put behaves like short stock in a real downtrend. Research source:
Antigravity CLI, 2026-09-02 (ranked #2 of 4)."""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common

UNDERLYING = "SPY"
ENTRY_INTERVAL_DAYS = 14
# DEVIATION FROM RESEARCH (2026-09-02): research proposed 30-45 DTE / ~monthly entries; this
# account's SPY options data has essentially no trade prints earlier than ~14 days before a
# contract's own expiry (confirmed by direct testing - see pmcc_diagonal.py's module docstring).
# 12 DTE keeps a 2-day safety margin, and entries every 14 days (vs. the original ~28) keep
# exposure roughly continuous given the much shorter hold.
TARGET_DTE = 12
PUT_DELTA = 0.18
CALL_DELTA = 0.35
PUT_WING = 5.0
RISK_PER_TRADE_PCT = 0.02
PROFIT_TAKE_PCT = 0.5  # close at 50% of max risk captured, consistent with the condor's exit rule
STOP_LOSS_MULTIPLE = 1.0


def run(lookback_weeks: int = 26) -> dict:
    today = date.today()
    history_start = today - timedelta(weeks=lookback_weeks + 12)
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
        if regime != "bull":
            skipped.append({"entry_date": entry_str, "reason": "regime_not_bull", "regime": regime})
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

        built = common.build_risk_reversal(UNDERLYING, expiry, spot, T, sigma, PUT_DELTA, CALL_DELTA, PUT_WING, data_start, data_end)
        if not built:
            skipped.append({"entry_date": entry_str, "reason": "no_liquid_contracts"})
            continue

        entry_value = common.value_risk_reversal(built["bars"], entry_str)
        if entry_value is None:
            skipped.append({"entry_date": entry_str, "reason": "missing_entry_print"})
            continue
        # Max loss dominated by the short-put-with-wing side (bounded at the wing width, net of
        # whatever credit/debit the whole 3-leg structure was opened for) - the long call's own
        # max loss is just its premium, already netted into entry_value. Documented approximation.
        max_loss_per_contract = PUT_WING - max(0.0, entry_value)
        if max_loss_per_contract <= 0:
            skipped.append({"entry_date": entry_str, "reason": "non_positive_max_loss", "entry_value": entry_value})
            continue

        trade = common.simulate_single_shot_trade(
            strategy="risk_reversal", structure="risk_reversal", built=built,
            entry_date=entry_date, expiry=expiry, value_fn=common.value_risk_reversal,
            max_loss_per_contract=max_loss_per_contract, risk_budget_pct=RISK_PER_TRADE_PCT,
            profit_take_pct=PROFIT_TAKE_PCT, stop_loss_multiple=STOP_LOSS_MULTIPLE,
        )
        if trade:
            trade.meta = {"spot_at_entry": spot, "sigma_at_entry": sigma, "regime": regime}
            trades.append(trade.__dict__)
        else:
            skipped.append({"entry_date": entry_str, "reason": "trade_construction_failed"})

    return {"strategy": "risk_reversal", "trades": trades, "skipped": skipped}
