"""Shared intraday indicators computed from 5-min SPY bars for a single trading day."""
import numpy as np


def typical_price(bar: dict) -> float:
    return (bar["h"] + bar["l"] + bar["c"]) / 3.0


def vwap_series(bars: list[dict]) -> list[dict]:
    """Returns a list parallel to `bars`, each entry {t, vwap, std} computed cumulatively
    from the start of the day (VWAP resets every morning by construction, since `bars` is
    always a single day's worth)."""
    cum_pv = 0.0
    cum_vol = 0.0
    cum_sq = 0.0
    out = []
    for bar in bars:
        tp = typical_price(bar)
        vol = bar["v"] or 1  # guard against a zero-volume bar
        cum_pv += tp * vol
        cum_vol += vol
        vwap = cum_pv / cum_vol
        cum_sq += vol * (tp - vwap) ** 2
        std = (cum_sq / cum_vol) ** 0.5
        out.append({"t": bar["t"], "vwap": vwap, "std": std, "close": bar["c"]})
    return out


def opening_range(bars: list[dict], num_bars: int = 6) -> dict | None:
    """First `num_bars` 5-min bars = 30 minutes (9:30-10:00 ET)."""
    window = bars[:num_bars]
    if not window:
        return None
    high = max(b["h"] for b in window)
    low = min(b["l"] for b in window)
    return {"high": high, "low": low, "mid": (high + low) / 2, "range_pct": (high - low) / low}


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI over the trailing `period` closes."""
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes[-(period + 1):])
    gains = deltas[deltas > 0].sum() / period
    losses = -deltas[deltas < 0].sum() / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - (100 / (1 + rs))


def volume_sma(bars: list[dict], index: int, window: int = 20) -> float | None:
    start = max(0, index - window)
    slice_ = bars[start:index]
    if not slice_:
        return None
    return sum(b["v"] for b in slice_) / len(slice_)


def log_returns_5min(bars: list[dict]) -> list[float]:
    """5-min log returns for one day's bars - the building block for a same-timescale
    realized-vol estimate (as opposed to daily-close RV, which is a different regime)."""
    closes = [b["c"] for b in bars]
    if len(closes) < 2:
        return []
    return list(np.diff(np.log(closes)))


BARS_PER_TRADING_DAY_5MIN = 78  # 6.5 hours * 12 five-minute bars/hour


def annualize_5min_returns(returns: list[float]) -> float:
    """Annualizes a pool of 5-min log returns using the correct high-frequency scaling
    (sqrt(252 trading days * 78 bars/day)) - NOT sqrt(252), which is for daily returns and
    would understate intraday vol by roughly a factor of sqrt(78)."""
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns) * np.sqrt(252 * BARS_PER_TRADING_DAY_5MIN))
