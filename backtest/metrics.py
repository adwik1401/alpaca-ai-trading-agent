"""Evaluation metrics that matter for judging, per research: raw P&L alone isn't enough -
Sharpe/Sortino/max-drawdown/profit-factor prove the edge is real and the risk gates work.

IMPORTANT: `returns` here is a PER-TRADE return series (one iron condor cycle each, spanning
several days), not a daily return series. Annualizing with a hardcoded sqrt(252) - as an earlier
version of this file did - silently assumes the strategy trades every single trading day, which
inflated the reported Sharpe/Sortino by roughly 3-5x for a strategy that actually trades 11-26
times a year. `periods_per_year` must be the strategy's actual trade frequency (trades / years
of lookback), not the calendar-day count. Caught and fixed 2026-09-02 when a user sanity-check
question ("are these good results?") prompted comparing the Sharpe against real-world
benchmarks - a reported Sharpe of ~11 was implausible on its face."""
import numpy as np


def sharpe_ratio(returns: list[float], periods_per_year: float, risk_free_per_period: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = np.array(returns) - risk_free_per_period
    std = np.std(excess)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(periods_per_year))


def sortino_ratio(returns: list[float], periods_per_year: float, risk_free_per_period: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    excess = np.array(returns) - risk_free_per_period
    downside = excess[excess < 0]
    downside_std = np.std(downside) if len(downside) > 0 else 0.0
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess) / downside_std * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: list[float]) -> float:
    """Returns max drawdown as a positive fraction (e.g. 0.04 = 4% drawdown)."""
    if not equity_curve:
        return 0.0
    curve = np.array(equity_curve)
    running_max = np.maximum.accumulate(curve)
    drawdowns = (running_max - curve) / running_max
    return float(np.max(drawdowns))


def profit_factor(trade_pnls: list[float]) -> float:
    gains = sum(p for p in trade_pnls if p > 0)
    losses = abs(sum(p for p in trade_pnls if p < 0))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def win_rate(trade_pnls: list[float]) -> float:
    if not trade_pnls:
        return 0.0
    return sum(1 for p in trade_pnls if p > 0) / len(trade_pnls)


def summarize(trade_pnls: list[float], equity_curve: list[float], returns: list[float], lookback_years: float) -> dict:
    periods_per_year = len(trade_pnls) / lookback_years if lookback_years > 0 else 0
    return {
        "num_trades": len(trade_pnls),
        "total_pnl": round(sum(trade_pnls), 2),
        "win_rate": round(win_rate(trade_pnls), 3),
        "profit_factor": round(profit_factor(trade_pnls), 3) if profit_factor(trade_pnls) != float("inf") else None,
        "sharpe": round(sharpe_ratio(returns, periods_per_year), 3),
        "sortino": round(sortino_ratio(returns, periods_per_year), 3),
        "max_drawdown_pct": round(max_drawdown(equity_curve) * 100, 3),
        "trades_per_year": round(periods_per_year, 1),
    }
