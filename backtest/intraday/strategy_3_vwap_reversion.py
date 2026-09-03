"""Strategy 3: Intraday VWAP mean-reversion credit spreads ("fading the bands").
Simplification: exits on the standard profit-take/stop-loss/hard-close rules rather than the
research's "close when spot touches VWAP baseline" rule - achieves the same risk-management
intent without needing to track spot and option value in lockstep. Documented, not hidden."""
from datetime import date

from . import data, indicators, common
from .common import IntradayTrade, is_past_hard_close, size_position, find_liquid_strike

NUM_STD = 2.0
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
SPREAD_WIDTH = 1.0
PROFIT_TAKE_PCT = 0.7  # mid of research's 60-80% credit decay
STOP_LOSS_MULTIPLE = 1.5
COOLDOWN_BARS = 3  # avoid re-entering immediately after an exit within the same day


def _open_credit_vertical(day: date, right: str, near_strike_target: float, far_strike_target: float, entry_time: str):
    """near = the strike we SELL (closer to spot), far = the strike we BUY (further OTM,
    protective wing). Returns (structure, entry_credit) or None if not tradeable."""
    near = find_liquid_strike(day, right, near_strike_target)
    far = find_liquid_strike(day, right, far_strike_target)
    if not near or not far:
        return None
    near_symbol, near_bars = near
    far_symbol, far_bars = far
    near_price = near_bars.get(entry_time, {}).get("c")
    far_price = far_bars.get(entry_time, {}).get("c")
    if not near_price or not far_price:
        return None
    entry_credit = near_price - far_price
    if entry_credit <= 0:
        return None
    # Unambiguous naming: "sold" = the near strike we sold, "bought" = the far wing we bought
    # as protection. Do NOT reuse common.price_vertical_at here - it computes (long - short)
    # for a DEBIT spread's "long"=near/expensive convention, which is the opposite of a credit
    # spread's near/sold leg - reusing it silently flips the sign (caught 2026-09-02: it made
    # every trade "profit-take" within minutes on pure noise, a false 100% win rate).
    structure = {
        "legs": {"sold": near_symbol, "bought": far_symbol},
        "bars": {"sold": near_bars, "bought": far_bars},
        "strikes": {"sold": float(near_symbol[-8:]) / 1000, "bought": float(far_symbol[-8:]) / 1000},
    }
    return structure, entry_credit


def _price_credit_vertical_at(bars_by_leg: dict, t: str) -> float | None:
    try:
        sold_price = bars_by_leg["sold"][t]["c"]
        bought_price = bars_by_leg["bought"][t]["c"]
    except KeyError:
        return None
    return sold_price - bought_price  # matches entry_credit's definition exactly


def _simulate_credit_vertical(day: date, structure: dict, entry_time: str, entry_credit: float, contracts: int, all_times: list[str]) -> IntradayTrade:
    trade = IntradayTrade(
        day=day.isoformat(), strategy="vwap_mean_reversion", structure="credit_spread",
        legs=structure["legs"], strikes=structure["strikes"], contracts=contracts,
        entry_time=entry_time, entry_price=entry_credit,
    )
    last_value = entry_credit
    for t in all_times:
        if t <= entry_time:
            continue
        val = _price_credit_vertical_at(structure["bars"], t)
        if val is None:
            continue
        last_value = val
        captured = entry_credit - val
        if captured >= PROFIT_TAKE_PCT * entry_credit:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "profit_take"
            break
        if (val - entry_credit) >= STOP_LOSS_MULTIPLE * entry_credit:
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "stop_loss"
            break
        if is_past_hard_close(t):
            trade.exit_time, trade.exit_price, trade.exit_reason = t, val, "hard_time_stop"
            break
    if trade.exit_time is None:
        trade.exit_time, trade.exit_price, trade.exit_reason = all_times[-1], last_value, "eod_forced_close"
    trade.pnl = (entry_credit - trade.exit_price) * 100 * contracts
    return trade


def run(days: list[date]) -> dict:
    trades, skipped = [], []
    for day in days:
        bars = data.get_intraday_equity_bars(day)
        if len(bars) < 20:
            skipped.append({"day": day.isoformat(), "reason": "insufficient_intraday_bars"})
            continue

        vwap = indicators.vwap_series(bars)
        closes = [b["c"] for b in bars]
        all_times = [b["t"] for b in bars]

        day_trade_count = 0
        blocked_until_idx = -1
        for i in range(14, len(bars)):
            if i <= blocked_until_idx:
                continue
            bar = bars[i]
            close = bar["c"]
            upper = vwap[i]["vwap"] + NUM_STD * vwap[i]["std"]
            lower = vwap[i]["vwap"] - NUM_STD * vwap[i]["std"]
            r = indicators.rsi(closes[: i + 1])
            if r is None:
                continue
            volume_declining = bar["v"] < bars[i - 1]["v"]

            overbought = bar["h"] >= upper and r > RSI_OVERBOUGHT and volume_declining
            oversold = bar["l"] <= lower and r < RSI_OVERSOLD and volume_declining
            if not (overbought or oversold):
                continue

            right = "C" if overbought else "P"
            near_target = close * (1 + 0.0025) if overbought else close * (1 - 0.0025)  # ~0.20 delta proxy
            far_target = near_target + SPREAD_WIDTH if overbought else near_target - SPREAD_WIDTH

            opened = _open_credit_vertical(day, right, near_target, far_target, bar["t"])
            if not opened:
                continue
            structure, entry_credit = opened
            wing_width = abs(structure["strikes"]["sold"] - structure["strikes"]["bought"])
            max_loss = wing_width - entry_credit
            contracts = size_position(max_loss)
            if contracts < 1:
                continue

            trade = _simulate_credit_vertical(day, structure, bar["t"], entry_credit, contracts, all_times)
            trades.append(trade.__dict__)
            day_trade_count += 1
            blocked_until_idx = i + COOLDOWN_BARS

        if day_trade_count == 0:
            skipped.append({"day": day.isoformat(), "reason": "no_band_touch_confirmed"})

    return {"strategy": "vwap_mean_reversion", "trades": trades, "skipped": skipped}
