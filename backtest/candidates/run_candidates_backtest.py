"""Run all 4 return-competitive candidate strategies (researched 2026-09-02 as challengers to the
live Hybrid VRP+Skew strategy) over the same 6-month lookback and score them against real historical
SPY option/equity data, plus a SPY buy-and-hold benchmark for the same window.
Usage: python -m backtest.candidates.run_candidates_backtest [lookback_weeks]
"""
import sys
import json
from datetime import date, timedelta
from pathlib import Path

from .. import data, metrics
from ..strategies.common import STARTING_NAV
from . import barbell_call_spread, momentum_vertical, risk_reversal, pmcc_diagonal

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def score_discrete(result: dict, lookback_years: float) -> dict:
    """Same scoring approach as the weekly engine's run_backtest.score(), but sorts trades by
    EXIT date (not entry/iteration order) before building the equity curve - these candidates can
    hold multiple overlapping tranches at once (e.g. barbell's staggered 2-week entries), so PnL
    realizes out of entry order and a naive cumulative sum would misstate drawdown timing."""
    trades = sorted(result["trades"], key=lambda t: t["exit_date"])
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


def score_pmcc(result: dict) -> dict:
    """PMCC is one continuously-rolled position, not discrete trades - scored from its own weekly
    equity curve. periods_per_year=52 is correct here (marks are genuinely weekly), unlike the
    per-trade-frequency annualization the other 3 candidates and the live Hybrid strategy use.
    NOT directly comparable Sharpe-to-Sharpe with those without accounting for that difference in
    marking frequency - see the module docstring in pmcc_diagonal.py."""
    returns = result["weekly_returns"]
    values = [v for _, v in result["equity_curve"]]
    sharpe = metrics.sharpe_ratio(returns, periods_per_year=52)
    sortino = metrics.sortino_ratio(returns, periods_per_year=52)
    dd = metrics.max_drawdown([STARTING_NAV] + values) if values else 0.0
    return {
        "strategy": "pmcc_diagonal",
        "num_trades": result["num_rolls"],
        "total_pnl": result["total_pnl"],
        "win_rate": None,
        "profit_factor": None,
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown_pct": round(dd * 100, 3),
        "trades_per_year": None,
        "skipped_count": len(result["skipped"]),
        "final_nav": result["final_nav"],
        "return_pct": result["return_pct"],
        "note": "Sharpe/Sortino computed on WEEKLY marks (periods_per_year=52), not per-trade frequency - see module docstring.",
    }


def spy_buy_and_hold(lookback_weeks: int) -> dict:
    today = date.today()
    start = today - timedelta(weeks=lookback_weeks)
    bars = data.get_equity_bars("SPY", start.isoformat(), (today + timedelta(days=1)).isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in bars}
    sorted_dates = sorted(closes_by_date.keys())
    if not sorted_dates:
        return {"error": "no_equity_data"}
    start_price = closes_by_date[sorted_dates[0]]
    end_price = closes_by_date[sorted_dates[-1]]
    equity_curve = [STARTING_NAV * (closes_by_date[d] / start_price) for d in sorted_dates]
    dd = metrics.max_drawdown(equity_curve)
    return {
        "strategy": "spy_buy_and_hold",
        "start_date": sorted_dates[0],
        "end_date": sorted_dates[-1],
        "start_price": start_price,
        "end_price": end_price,
        "return_pct": round((end_price - start_price) / start_price * 100, 2),
        "max_drawdown_pct": round(dd * 100, 3),
    }


def main():
    lookback_weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 26
    lookback_years = lookback_weeks / 52

    print(f"Running the 4 candidate strategies over the last {lookback_weeks} weeks of real SPY options data...\n")

    scoreboard = []

    for name, module in [("barbell_call_spread", barbell_call_spread), ("momentum_vertical", momentum_vertical), ("risk_reversal", risk_reversal)]:
        print(f"--- {name} ---")
        result = module.run(lookback_weeks=lookback_weeks)
        (RESULTS_DIR / f"{name}.json").write_text(json.dumps(result, indent=2, default=str))
        print(f"  trades: {len(result['trades'])}, skipped: {len(result['skipped'])}")
        s = score_discrete(result, lookback_years)
        scoreboard.append(s)

    print("--- pmcc_diagonal ---")
    pmcc_result = pmcc_diagonal.run(lookback_weeks=lookback_weeks)
    (RESULTS_DIR / "pmcc_diagonal.json").write_text(json.dumps(pmcc_result, indent=2, default=str))
    print(f"  rolls: {pmcc_result['num_rolls']}, skipped: {len(pmcc_result['skipped'])}, contracts: {pmcc_result['contracts']}")
    scoreboard.append(score_pmcc(pmcc_result))

    benchmark = spy_buy_and_hold(lookback_weeks)

    print("\n=== SCOREBOARD ===")
    for s in scoreboard:
        trades_str = f"{s['num_trades']:3d}" if s['num_trades'] is not None else "  -"
        wr = f"{s['win_rate']:.2%}" if s.get('win_rate') is not None else "n/a"
        pf = s.get('profit_factor')
        pf_str = f"{pf}" if pf is not None else "n/a"
        print(
            f"{s['strategy']:20s} | trades={trades_str} | pnl=${s['total_pnl']:>10,.2f} ({s['return_pct']}%) | "
            f"win_rate={wr} | profit_factor={pf_str} | "
            f"sharpe={s['sharpe']:.2f} | sortino={s['sortino']:.2f} | max_dd={s['max_drawdown_pct']:.2f}%"
        )
    print(f"\n{'spy_buy_and_hold':20s} | return={benchmark.get('return_pct', 'n/a')}% | max_dd={benchmark.get('max_drawdown_pct', 'n/a')}% "
          f"({benchmark.get('start_date')} @ ${benchmark.get('start_price')} -> {benchmark.get('end_date')} @ ${benchmark.get('end_price')})")

    scoreboard.append(benchmark)
    (RESULTS_DIR / "scoreboard.json").write_text(json.dumps(scoreboard, indent=2, default=str))
    print(f"\nFull results saved to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
