"""Alpaca market data access for backtesting. Real historical data only - no synthetic fallback needed
(confirmed 2026-09-01: Alpaca returns real historical option bars for expired contracts)."""
import os
import json
import hashlib
from pathlib import Path
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

TRADING_BASE = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"


def _headers() -> dict:
    """Lazy (not module-level) so importing this module - e.g. transitively, for DATA_BASE/
    TRADING_BASE or a single pure function like delta_offset_pct - never requires
    ALPACA_API_KEY/ALPACA_SECRET_KEY (this project's dev-account credentials) to be present.
    Real callers of the functions below still need them at call time, same as before - this only
    defers *when* they're read. Bug found 2026-09-03: the live agent's GitHub Actions workflow
    deliberately sets only the submission account's credentials (not dev's), and
    agent/governor.py transitively imports this module via backtest.strategies.common just for
    delta_offset_pct - the old module-level read made that import fail in CI with a KeyError on
    ALPACA_API_KEY despite the agent never calling any function that needs it."""
    return {
        "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
        "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"],
    }


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


def get_equity_bars(symbol: str, start: str, end: str, timeframe: str = "1Day") -> list[dict]:
    """Daily OHLCV bars for the underlying. Returns list of {t,o,h,l,c,v} sorted by time."""
    cache_key = f"equity_bars:{symbol}:{start}:{end}:{timeframe}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    bars = []
    page_token = None
    while True:
        params = {"timeframe": timeframe, "start": start, "end": end, "limit": 1000, "feed": "iex"}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(f"{DATA_BASE}/v2/stocks/{symbol}/bars", headers=_headers(), params=params)
        r.raise_for_status()
        d = r.json()
        bars.extend(d.get("bars", []))
        page_token = d.get("next_page_token")
        if not page_token:
            break

    _cache_set(cache_key, bars)
    return bars


def get_option_bars(symbols: list[str], start: str, end: str, timeframe: str = "1Day") -> dict[str, list[dict]]:
    """Historical bars per option contract symbol. Returns {symbol: [bars]}. Missing/invalid
    symbols simply return an empty list (contract never traded, wrong strike, etc.)."""
    result = {}
    # Alpaca allows up to 100 symbols per request
    for i in range(0, len(symbols), 100):
        batch = symbols[i : i + 100]
        cache_key = f"option_bars:{','.join(sorted(batch))}:{start}:{end}:{timeframe}"
        cached = _cache_get(cache_key)
        if cached is not None:
            result.update(cached)
            continue

        batch_result = {s: [] for s in batch}
        page_token = None
        while True:
            params = {
                "symbols": ",".join(batch),
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "limit": 10000,
            }
            if page_token:
                params["page_token"] = page_token
            r = requests.get(f"{DATA_BASE}/v1beta1/options/bars", headers=_headers(), params=params)
            r.raise_for_status()
            d = r.json()
            for sym, bars in d.get("bars", {}).items():
                batch_result[sym] = batch_result.get(sym, []) + bars
            page_token = d.get("next_page_token")
            if not page_token:
                break

        _cache_set(cache_key, batch_result)
        result.update(batch_result)

    return result


def get_option_chain_snapshot(underlying: str, expiration_gte: str = None, expiration_lte: str = None) -> dict:
    """Current snapshot (greeks + latest quote) for the live option chain. Used as a static
    proxy for open-interest/gamma structure since Alpaca has no historical-OI endpoint - see
    architecture-decisions.md / backtest-results.md for the caveat this introduces on GEX."""
    cache_key = f"chain_snapshot:{underlying}:{expiration_gte}:{expiration_lte}:{date.today().isoformat()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    snapshots = {}
    page_token = None
    params = {"limit": 1000}
    if expiration_gte:
        params["expiration_date_gte"] = expiration_gte
    if expiration_lte:
        params["expiration_date_lte"] = expiration_lte
    while True:
        if page_token:
            params["page_token"] = page_token
        r = requests.get(
            f"{DATA_BASE}/v1beta1/options/snapshots/{underlying}", headers=_headers(), params=params
        )
        r.raise_for_status()
        d = r.json()
        snapshots.update(d.get("snapshots", {}))
        page_token = d.get("next_page_token")
        if not page_token:
            break

    _cache_set(cache_key, snapshots)
    return snapshots


def construct_option_symbol(underlying: str, expiry: date, right: str, strike: float) -> str:
    """Build an OSI-format Alpaca option symbol: TICKER + YYMMDD + C/P + 8-digit strike*1000."""
    strike_int = round(strike * 1000)
    return f"{underlying}{expiry.strftime('%y%m%d')}{right.upper()}{strike_int:08d}"


def get_latest_trade_price(symbol: str) -> float:
    r = requests.get(f"{DATA_BASE}/v2/stocks/{symbol}/trades/latest", headers=_headers())
    r.raise_for_status()
    return r.json()["trade"]["p"]
