"""Intraday data access for the 6-month backtest of all 4 candidate strategies. Uses 5-minute
bars (not 1-minute) to keep the number of API calls and in-memory data tractable across ~126
trading days x 4 strategies x up to 4 option legs each - a real tradeoff of fidelity for
feasibility given the time available, documented here rather than silently assumed."""
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from backtest.data import _headers, DATA_BASE, TRADING_BASE  # reuse auth/base URLs (lazy headers)

ET = ZoneInfo("America/New_York")
CACHE_DIR = Path(__file__).resolve().parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_get(key: str):
    path = CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    return None


def _cache_set(key: str, value):
    path = CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    path.write_text(json.dumps(value))


def market_open_close_utc(day: date) -> tuple[str, str]:
    open_et = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
    close_et = datetime(day.year, day.month, day.day, 16, 0, tzinfo=ET)
    return open_et.astimezone(ZoneInfo("UTC")).isoformat(), close_et.astimezone(ZoneInfo("UTC")).isoformat()


def get_trading_days(start: date, end: date) -> list[date]:
    """Real trading-day calendar derived from actual SPY daily bars - avoids needing a
    separate holiday calendar."""
    cache_key = f"trading_days:{start}:{end}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return [date.fromisoformat(d) for d in cached]

    r = requests.get(
        f"{DATA_BASE}/v2/stocks/SPY/bars",
        headers=_headers(),
        params={"timeframe": "1Day", "start": start.isoformat(), "end": end.isoformat(), "limit": 1000, "feed": "iex"},
    )
    r.raise_for_status()
    days = [b["t"][:10] for b in r.json().get("bars", [])]
    _cache_set(cache_key, days)
    return [date.fromisoformat(d) for d in days]


def get_intraday_equity_bars(day: date, timeframe: str = "5Min") -> list[dict]:
    cache_key = f"intraday_equity:{day}:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start, end = market_open_close_utc(day)
    r = requests.get(
        f"{DATA_BASE}/v2/stocks/SPY/bars",
        headers=_headers(),
        params={"timeframe": timeframe, "start": start, "end": end, "limit": 200, "feed": "iex"},
    )
    r.raise_for_status()
    bars = r.json().get("bars", [])
    _cache_set(cache_key, bars)
    return bars


def get_intraday_option_bars(symbols: list[str], day: date, timeframe: str = "5Min") -> dict[str, list[dict]]:
    if not symbols:
        return {}
    cache_key = f"intraday_option:{','.join(sorted(symbols))}:{day}:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    start, end = market_open_close_utc(day)
    result = {s: [] for s in symbols}
    r = requests.get(
        f"{DATA_BASE}/v1beta1/options/bars",
        headers=_headers(),
        params={"symbols": ",".join(symbols), "timeframe": timeframe, "start": start, "end": end, "limit": 10000},
    )
    r.raise_for_status()
    for sym, bars in r.json().get("bars", {}).items():
        result[sym] = bars
    _cache_set(cache_key, result)
    return result


def construct_0dte_symbol(day: date, right: str, strike: float) -> str:
    strike_int = round(strike * 1000)
    return f"SPY{day.strftime('%y%m%d')}{right.upper()}{strike_int:08d}"
