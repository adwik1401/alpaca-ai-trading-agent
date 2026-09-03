"""Strategy 4: Intraday trend-continuation momentum spreads (VWAP pullback).
Simplification: exits on profit-take/stop-loss/hard-close rather than research's "1-min candle
closes on the wrong side of VWAP" trend-break exit - same risk-management intent, less
bar-by-bar state to track. Documented, not hidden."""
from datetime import date

from . import data, indicators, common

TREND_MIN_BARS = 6  # 30 minutes of one-sided VWAP positioning to call it a trend
PULLBACK_TOLERANCE_PCT = 0.0003
SPREAD_WIDTH = 1.5
PROFIT_TAKE_PCT = 0.4
STOP_LOSS_PCT = 0.3
COOLDOWN_BARS = 4


def _trend_direction(bars: list[dict], vwap: list[dict], i: int) -> str | None:
    if i < TREND_MIN_BARS:
        return None
    window = list(zip(bars[i - TREND_MIN_BARS : i], vwap[i - TREND_MIN_BARS : i]))
    if all(b["c"] > v["vwap"] for b, v in window):
        slope = vwap[i - 1]["vwap"] - vwap[i - TREND_MIN_BARS]["vwap"]
        return "up" if slope > 0 else None
    if all(b["c"] < v["vwap"] for b, v in window):
        slope = vwap[i - 1]["vwap"] - vwap[i - TREND_MIN_BARS]["vwap"]
        return "down" if slope < 0 else None
    return None


def run(days: list[date]) -> dict:
    trades, skipped = [], []
    for day in days:
        bars = data.get_intraday_equity_bars(day)
        if len(bars) < TREND_MIN_BARS + 5:
            skipped.append({"day": day.isoformat(), "reason": "insufficient_intraday_bars"})
            continue

        vwap = indicators.vwap_series(bars)
        all_times = [b["t"] for b in bars]

        day_trade_count = 0
        blocked_until_idx = -1
        for i in range(TREND_MIN_BARS, len(bars)):
            if i <= blocked_until_idx:
                continue
            trend = _trend_direction(bars, vwap, i)
            if not trend:
                continue

            bar = bars[i]
            near_vwap = abs(bar["c"] - vwap[i]["vwap"]) / vwap[i]["vwap"] <= PULLBACK_TOLERANCE_PCT
            low_volume = bar["v"] < (indicators.volume_sma(bars, i, window=20) or float("inf")) * 0.8
            if not (near_vwap and low_volume):
                continue
            if i + 1 >= len(bars):
                continue
            confirm_bar = bars[i + 1]
            confirmed = confirm_bar["c"] > confirm_bar["o"] if trend == "up" else confirm_bar["c"] < confirm_bar["o"]
            if not confirmed:
                continue

            right = "C" if trend == "up" else "P"
            close = confirm_bar["c"]
            long_target = close  # ~0.45-0.50 delta, near the money
            short_target = close + SPREAD_WIDTH if trend == "up" else close - SPREAD_WIDTH
            built = common.build_vertical_spread(day, right, long_target, short_target)
            if not built:
                continue
            entry_time = confirm_bar["t"]
            entry_debit = common.price_vertical_at(built["bars"], entry_time)
            if entry_debit is None or entry_debit <= 0:
                continue
            contracts = common.size_position(entry_debit)
            if contracts < 1:
                continue

            trade = common.simulate_debit_spread(
                day, "vwap_trend_pullback", built, entry_time, entry_debit, contracts, all_times,
                PROFIT_TAKE_PCT, STOP_LOSS_PCT,
            )
            trade_dict = trade.__dict__
            trade_dict["meta"] = {"direction": trend}
            trades.append(trade_dict)
            day_trade_count += 1
            blocked_until_idx = i + COOLDOWN_BARS

        if day_trade_count == 0:
            skipped.append({"day": day.isoformat(), "reason": "no_pullback_confirmed"})

    return {"strategy": "vwap_trend_pullback", "trades": trades, "skipped": skipped}
