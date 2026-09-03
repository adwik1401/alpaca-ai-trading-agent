"""Run all 4 intraday strategy candidates over the same trading-day window and score them.
Usage: python -m backtest.intraday.run_intraday_backtest [num_trading_days]
Pass a small number (e.g. 5) first to validate the pipeline before running the full 6 months
(~126 trading days) - intraday backtesting means a fresh 0DTE option chain lookup per day,
so this is much heavier on API calls than the weekly backtest was.
"""
import sys
import json
from datetime import date, timedelta
from pathlib import Path

from backtest import metrics
from . import data
from . import strategy_1_iron_condor, strategy_2_orb_breakout, strategy_3_vwap_reversion, strategy_4_vwap_pullback

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

STARTING_NAV = 100_000.0


def score(result: dict, lookback_years: float) -> dict:
    trades = result["trades"]
    pnls = [t["pnl"] for t in trades]
    equity_curve = [STARTING_NAV]
    for pnl in pnls:
        equity_curve.append(equity_curve[-1] + pnl)
    returns = [pnls[i] / equity_curve[i] for i in range(len(pnls))] if pnls else []
    summary = metrics.summarize(pnls, equity_curve, returns, lookback_years)
    summary["strategy"] = result["strategy"]
    summary["skipped_days"] = len(result["skipped"])
    summary["final_nav"] = round(equity_curve[-1], 2)
    summary["return_pct"] = round((equity_curve[-1] - STARTING_NAV) / STARTING_NAV * 100, 2)
    return summary


def main():
    num_days = int(sys.argv[1]) if len(sys.argv) > 1 else 126  # ~126 trading days = 6 months
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=int(num_days * 1.45) + 10)  # buffer for weekends/holidays

    all_trading_days = data.get_trading_days(start, end)
    trading_days = all_trading_days[-num_days:]
    print(f"Running intraday backtests over {len(trading_days)} trading days ({trading_days[0]} to {trading_days[-1]})...\n")
    lookback_years = len(trading_days) / 252

    strategies = [
        ("0dte_iron_condor", strategy_1_iron_condor),
        ("orb_breakout", strategy_2_orb_breakout),
        ("vwap_mean_reversion", strategy_3_vwap_reversion),
        ("vwap_trend_pullback", strategy_4_vwap_pullback),
    ]

    results = {}
    for name, module in strategies:
        print(f"--- {name} ---")
        result = module.run(trading_days)
        results[name] = result
        (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2, default=str))
        print(f"  trades: {len(result['trades'])}, days skipped: {len(result['skipped'])}")

    print("\n=== SCOREBOARD ===")
    scoreboard = []
    for name, result in results.items():
        s = score(result, lookback_years)
        scoreboard.append(s)
        pf = s["profit_factor"] if s["profit_factor"] is not None else float("inf")
        print(
            f"{s['strategy']:22s} | trades={s['num_trades']:3d} ({s['trades_per_year']}/yr) | "
            f"pnl=${s['total_pnl']:>10,.2f} ({s['return_pct']}%) | win_rate={s['win_rate']:.2%} | "
            f"profit_factor={pf} | sharpe={s['sharpe']:.2f} | max_dd={s['max_drawdown_pct']:.2f}%"
        )

    (RESULTS_DIR / "scoreboard.json").write_text(json.dumps(scoreboard, indent=2, default=str))
    print(f"\nFull results saved to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
