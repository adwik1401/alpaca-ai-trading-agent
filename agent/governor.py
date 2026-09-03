"""Governor layer: deterministic strike selection and position sizing. The LLM never picks
strikes or prices anything - it only classifies regime (see analyst.py). This module scans the
LIVE option chain for real, tradeable contracts near the delta target and builds the exact
order plan the executor will submit.

Note on timing: with only ~2.5 days left in the hackathon as of 2026-09-02, there is exactly
one weekly SPY expiry (2026-09-04) left before the deadline - so unlike the backtest's
Monday-only entry cadence, this module is designed to be checked on every scheduled run and
fire as soon as conditions are met, not wait for a specific weekday."""
from datetime import date, timedelta

import requests

from backtest import black_scholes as bs
from backtest.strategies.common import delta_offset_pct
from . import config
from .executor import OrderLeg, CondorOrderPlan

DATA_BASE = "https://data.alpaca.markets"
TRADING_BASE = "https://paper-api.alpaca.markets"


def _headers():
    return {"APCA-API-KEY-ID": config.ALPACA_API_KEY, "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY}


def next_valid_expiry(today: date | None = None) -> date:
    """SPY has daily expiries, so we are not locked into 'next Friday' - and deliberately
    should not be. Our strike selection is Black-Scholes delta-targeting, which assumes
    continuous price diffusion and has no way to model jump risk from a scheduled binary
    event (e.g. Non-Farm Payrolls). Decided 2026-09-02: skip any expiry landing on a date in
    config.AVOID_EXPIRY_DATES rather than trade into an event our own risk model can't price.
    See architecture-decisions.md for the reasoning."""
    today = today or date.today()
    candidate = today + timedelta(days=1)  # minimum 1 DTE - a 0DTE entry has no real time value left to sell
    for _ in range(6):
        if candidate.weekday() < 5 and candidate.isoformat() not in config.AVOID_EXPIRY_DATES:
            return candidate
        candidate += timedelta(days=1)
    return candidate


def get_spot_price() -> float:
    r = requests.get(f"{DATA_BASE}/v2/stocks/{config.UNDERLYING}/trades/latest", headers=_headers())
    r.raise_for_status()
    return r.json()["trade"]["p"]


def get_realized_vol(window: int = 20) -> float:
    end = date.today()
    start = end - timedelta(days=window * 2 + 10)  # buffer for weekends/holidays
    r = requests.get(
        f"{DATA_BASE}/v2/stocks/{config.UNDERLYING}/bars",
        headers=_headers(),
        params={"timeframe": "1Day", "start": start.isoformat(), "end": end.isoformat(), "limit": 1000, "feed": "iex"},
    )
    r.raise_for_status()
    closes = [b["c"] for b in r.json().get("bars", [])]
    return bs.realized_vol(closes, window=window)


def get_chain_snapshot(expiry: date, strike_gte: float, strike_lte: float) -> dict:
    r = requests.get(
        f"{DATA_BASE}/v1beta1/options/snapshots/{config.UNDERLYING}",
        headers=_headers(),
        params={
            "expiration_date": expiry.isoformat(),
            "strike_price_gte": strike_gte,
            "strike_price_lte": strike_lte,
            "limit": 200,
        },
    )
    r.raise_for_status()
    return r.json().get("snapshots", {})


def _mid(quote: dict) -> float | None:
    bid, ask = quote.get("bp"), quote.get("ap")
    if not bid or not ask or bid <= 0 or ask <= 0:
        return None
    return (bid + ask) / 2


def _spread_pct(quote: dict, mid: float) -> float:
    bid, ask = quote.get("bp", 0), quote.get("ap", 0)
    return (ask - bid) / mid if mid else 1.0


def find_strike_near(snapshots: dict, right: str, target_strike: float, expiry: date) -> tuple[str, dict] | None:
    """Nearest strike to target with a real, tradeable (spread-filtered) quote."""
    candidates = []
    for symbol, snap in snapshots.items():
        if symbol[-9] != right:
            continue
        strike = float(symbol[-8:]) / 1000
        quote = snap.get("latestQuote", {})
        mid = _mid(quote)
        if mid is None:
            continue
        if _spread_pct(quote, mid) > config.MAX_SPREAD_PCT_OF_MID:
            continue  # risk gate: reject wide markets, don't even consider them
        candidates.append((abs(strike - target_strike), symbol, snap, strike))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, symbol, snap, _ = candidates[0]
    return symbol, snap


def build_live_condor_signal() -> dict:
    """Pulls live data and returns the entry signal + (if favorable) a ready order plan.
    Does not place any order - that's the executor's job, gated by risk_gates first."""
    expiry = next_valid_expiry()
    spot = get_spot_price()
    rv20 = get_realized_vol(20)
    T = max((expiry - date.today()).days, 1) / 365
    offset_pct = delta_offset_pct(rv20, T, config.TARGET_DELTA)

    call_target = spot * (1 + offset_pct)
    put_target = spot * (1 - offset_pct)
    snapshots = get_chain_snapshot(expiry, spot * (1 - offset_pct - 0.03), spot * (1 + offset_pct + 0.03))

    short_call = find_strike_near(snapshots, "C", call_target, expiry)
    short_put = find_strike_near(snapshots, "P", put_target, expiry)
    if not short_call or not short_put:
        return {"tradeable": False, "reason": "no_liquid_short_strikes", "expiry": expiry.isoformat()}

    sc_symbol, sc_snap = short_call
    sp_symbol, sp_snap = short_put
    sc_strike = float(sc_symbol[-8:]) / 1000
    sp_strike = float(sp_symbol[-8:]) / 1000

    lc_symbol = f"{config.UNDERLYING}{expiry.strftime('%y%m%d')}C{round((sc_strike + config.WING_WIDTH) * 1000):08d}"
    lp_symbol = f"{config.UNDERLYING}{expiry.strftime('%y%m%d')}P{round((sp_strike - config.WING_WIDTH) * 1000):08d}"

    wing_snapshots = get_chain_snapshot(expiry, sp_strike - config.WING_WIDTH - 1, sc_strike + config.WING_WIDTH + 1)
    lc_snap = wing_snapshots.get(lc_symbol)
    lp_snap = wing_snapshots.get(lp_symbol)
    if not lc_snap or not lp_snap:
        return {"tradeable": False, "reason": "no_liquid_wing_strikes", "expiry": expiry.isoformat()}

    sc_mid = _mid(sc_snap["latestQuote"])
    lc_mid = _mid(lc_snap["latestQuote"])
    sp_mid = _mid(sp_snap["latestQuote"])
    lp_mid = _mid(lp_snap["latestQuote"])
    if None in (sc_mid, lc_mid, sp_mid, lp_mid):
        return {"tradeable": False, "reason": "incomplete_quotes", "expiry": expiry.isoformat()}

    net_credit = (sc_mid - lc_mid) + (sp_mid - lp_mid)
    iv = bs.implied_vol(sc_mid, spot, sc_strike, T, "C")
    put_iv = bs.implied_vol(sp_mid, spot, sp_strike, T, "P")
    skew = (put_iv - iv) if (iv is not None and put_iv is not None) else None

    vrp_ok = iv is not None and (iv - rv20) >= config.IV_MINUS_RV_THRESHOLD
    # Skew rank needs history we don't have live yet on day one - conservative default:
    # treat skew_ok as true unless skew is clearly extreme (>2x typical historical range from
    # backtest, ~0.09) rather than blocking entirely for lack of a rolling sample.
    skew_ok = skew is None or skew < 0.09

    max_loss_per_contract = config.WING_WIDTH - net_credit
    plan = None
    if vrp_ok and skew_ok and net_credit > 0 and max_loss_per_contract > 0:
        plan = CondorOrderPlan(
            legs=[
                OrderLeg(symbol=sc_symbol, side="sell"),
                OrderLeg(symbol=lc_symbol, side="buy"),
                OrderLeg(symbol=sp_symbol, side="sell"),
                OrderLeg(symbol=lp_symbol, side="buy"),
            ],
            limit_price=round(net_credit, 2),
            contracts=1,  # sized by risk_gates.size_position before submission
        )

    return {
        "tradeable": plan is not None,
        "expiry": expiry.isoformat(),
        "spot": spot,
        "rv20": rv20,
        "iv": iv,
        "skew": skew,
        "net_credit": net_credit,
        "max_loss_per_contract": max_loss_per_contract,
        "vrp_ok": vrp_ok,
        "skew_ok": skew_ok,
        "plan": plan,
    }
