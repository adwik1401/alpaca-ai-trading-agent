"""Run all 3 candidate strategies over the same lookback window and score them.
Usage: python -m backtest.run_backtest [lookback_weeks]
"""
import sys
import json
from pathlib import Path

from . import metrics
from .strategies import vrp_iron_condor, skew_regime, hybrid
from .strategies.common import STARTING_NAV

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def score(result: dict, lookback_years: float) -> dict:
    trades = result["trades"]
    pnls = [t["pnl"] for t in trades]

    equity_curve = [STARTING_NAV]
    for pnl in pnls:
        equity_curve.append(equity_curve[-1] + pnl)

    returns = [pnls[i] / equity_curve[i] for i in range(len(pnls))] if pnls else []

    summary = metrics.summarize(pnls, equity_curve, returns, lookback_years)
    summary["strategy"] = result["strategy"]
    summary["skipped_count"] = len(result["skipped"])
    summary["final_nav"] = round(equity_curve[-1], 2)
    summary["return_pct"] = round((equity_curve[-1] - STARTING_NAV) / STARTING_NAV * 100, 2)
    return summary


def main():
    lookback_weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    lookback_years = lookback_weeks / 52

    print(f"Running backtests over the last {lookback_weeks} weeks of real SPY options data...\n")

    results = {}
    for name, module in [("vrp_iron_condor", vrp_iron_condor), ("skew_regime", skew_regime), ("hybrid", hybrid)]:
        print(f"--- {name} ---")
        result = module.run(lookback_weeks=lookback_weeks)
        results[name] = result
        (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2, default=str))
        print(f"  trades: {len(result['trades'])}, skipped: {len(result['skipped'])}")

    print("\n=== SCOREBOARD ===")
    scoreboard = []
    for name, result in results.items():
        s = score(result, lookback_years)
        scoreboard.append(s)
        print(
            f"{s['strategy']:20s} | trades={s['num_trades']:3d} ({s['trades_per_year']}/yr) | pnl=${s['total_pnl']:>10,.2f} ({s['return_pct']}%) | "
            f"win_rate={s['win_rate']:.2%} | profit_factor={s['profit_factor']} | "
            f"sharpe={s['sharpe']:.2f} | sortino={s['sortino']:.2f} | max_dd={s['max_drawdown_pct']:.2f}%"
        )

    (RESULTS_DIR / "scoreboard.json").write_text(json.dumps(scoreboard, indent=2, default=str))
    print(f"\nFull results saved to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
