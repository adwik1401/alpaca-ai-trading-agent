"""Train/test trading-day split for the 0DTE Iron Condor parameter search. The search (Phase 3
of .claude/plans/0dte-condor-parameter-tuning-plan.md) only ever evaluates candidate parameter
sets on the train split; the final chosen parameter set is validated on the held-out test split
before being proposed for application (Phase 4/5) - guards against overfitting the search to the
one ~1-year window of real data this account has access to."""
from datetime import date

from backtest.intraday import data

LOOKBACK_START = date(2026, 3, 4)  # same window as the original 6-month intraday backtest
LOOKBACK_END = date(2026, 9, 1)  # (see .claude/wiki/intraday-backtest-results.md)
TRAIN_FRACTION = 2 / 3  # ~84 train days / ~42 test days out of ~126 trading days


def train_test_split() -> tuple[list[date], list[date]]:
    """Real trading-day calendar (via backtest.intraday.data.get_trading_days, derived from
    actual SPY bars) split by day count, not calendar date - avoids a fixed date boundary landing
    unevenly across holidays."""
    all_days = data.get_trading_days(LOOKBACK_START, LOOKBACK_END)
    split_idx = round(len(all_days) * TRAIN_FRACTION)
    return all_days[:split_idx], all_days[split_idx:]
