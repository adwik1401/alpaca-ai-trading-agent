"""Deterministic option math. Never delegate this to an LLM (research finding:
LLMs have +-15-40% error rates on option math done in token space)."""
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

RISK_FREE_RATE = 0.045  # approx short-term T-bill yield, good enough for short-dated options


def bs_price(S: float, K: float, T: float, sigma: float, option_type: str, r: float = RISK_FREE_RATE) -> float:
    """Black-Scholes European option price. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(0.0, S - K) if option_type == "C" else max(0.0, K - S)
        return intrinsic
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option_type == "C":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def implied_vol(price: float, S: float, K: float, T: float, option_type: str, r: float = RISK_FREE_RATE) -> float | None:
    """Back out IV from an observed market price via Brent's method. Returns None if it can't
    be solved (e.g. price outside no-arbitrage bounds - happens with wide/stale quotes)."""
    if T <= 0 or price <= 0:
        return None
    intrinsic = max(0.0, S - K) if option_type == "C" else max(0.0, K - S)
    if price < intrinsic:
        return None

    def f(sigma):
        return bs_price(S, K, T, sigma, option_type, r) - price

    try:
        return brentq(f, 1e-4, 5.0, maxiter=100)
    except ValueError:
        return None


def greeks(S: float, K: float, T: float, sigma: float, option_type: str, r: float = RISK_FREE_RATE) -> dict:
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100  # per 1 vol point
    if option_type == "C":
        delta = norm.cdf(d1)
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)
        ) / 365
    else:
        delta = norm.cdf(d1) - 1
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)
        ) / 365
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def realized_vol(closes: list[float], window: int = 20) -> float:
    """Annualized realized volatility from daily closes (last `window` days of log returns)."""
    closes = np.array(closes[-(window + 1) :])
    if len(closes) < 2:
        return 0.0
    log_returns = np.diff(np.log(closes))
    return float(np.std(log_returns) * np.sqrt(252))


def iv_rank(current_iv: float, iv_history: list[float]) -> float:
    """Percentile rank of current IV within the historical IV sample, 0-100."""
    if not iv_history:
        return 50.0
    below = sum(1 for iv in iv_history if iv <= current_iv)
    return 100.0 * below / len(iv_history)
