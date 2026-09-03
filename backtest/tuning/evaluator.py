"""Objective evaluator: runs strategy_1_iron_condor against a fixed day range for a given
parameter set and scores it. Objective (decided during /explore): maximize Sharpe on that range,
subject to a hard max-drawdown cap matching agent/config.py's own TOTAL_DRAWDOWN_KILL_SWITCH_PCT
(0.06 = 6%) - a parameter set that breaches the cap is rejected regardless of how good its Sharpe
looks, same principle as the live agent's own kill switch."""
from datetime import date

from backtest import metrics
from backtest.intraday import strategy_1_iron_condor as strat

STARTING_NAV = 100_000.0
MAX_DRAWDOWN_CAP_PCT = 6.0  # matches agent/config.py TOTAL_DRAWDOWN_KILL_SWITCH_PCT
# A parameter set that only produces a handful of trades over 84 train days can show an
# eye-catching Sharpe purely from small-sample noise (this project already hit exactly this
# failure mode earlier - see the corrected-Sharpe note in backtest-results.md). 15 trades over
# the train window is a modest bar, not a rigorous one, but it's enough to stop the search from
# "improving" itself into an under-traded corner of the parameter space.
MIN_TRADES_FOR_ELIGIBILITY = 15


def evaluate(params: dict, days: list[date]) -> dict:
    result = strat.run(days, params=params)
    trades = result["trades"]
    pnls = [t["pnl"] for t in trades]

    equity_curve = [STARTING_NAV]
    for pnl in pnls:
        equity_curve.append(equity_curve[-1] + pnl)
    returns = [pnls[i] / equity_curve[i] for i in range(len(pnls))] if pnls else []

    # Same annualization convention as run_intraday_backtest.py's score() - trade frequency is
    # derived from the actual day-range length, not a fixed constant.
    lookback_years = len(days) / 252
    summary = metrics.summarize(pnls, equity_curve, returns, lookback_years)
    summary["return_pct"] = round((equity_curve[-1] - STARTING_NAV) / STARTING_NAV * 100, 2)
    summary["passes_drawdown_cap"] = summary["max_drawdown_pct"] <= MAX_DRAWDOWN_CAP_PCT
    summary["eligible"] = summary["num_trades"] >= MIN_TRADES_FOR_ELIGIBILITY
    summary["skipped_days"] = len(result["skipped"])
    summary["num_days"] = len(days)
    return summary
