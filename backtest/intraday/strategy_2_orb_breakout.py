"""Strategy 2: Opening Range Breakout (ORB) directional debit spreads.
Simplification vs. the full research spec: the "close back through ORB midpoint" exit rule
is not implemented (would require tracking spot and option value in lockstep bar-by-bar,
extra complexity for a secondary strategy) - profit-take/stop-loss/hard-close cover the same
risk-control intent. Documented here rather than silently dropped."""
from datetime import date

from . import data, indicators, common

BREAKOUT_THRESHOLD_PCT = 0.0005
VOLUME_CONFIRMATION_MULTIPLE = 1.5
SPREAD_WIDTH = 1.5  # midpoint of research's $1-2
PROFIT_TAKE_PCT = 0.6  # mid of 50-75% ROI on debit
STOP_LOSS_PCT = 0.45  # mid of 40-50%


def run(days: list[date]) -> dict:
    trades, skipped = [], []
    for day in days:
        bars = data.get_intraday_equity_bars(day)
        if len(bars) < 10:
            skipped.append({"day": day.isoformat(), "reason": "insufficient_intraday_bars"})
            continue

        orb = indicators.opening_range(bars)
        if not orb:
            skipped.append({"day": day.isoformat(), "reason": "no_opening_range"})
            continue
        vwap = indicators.vwap_series(bars)

        entered = False
        for i in range(6, len(bars)):
            bar = bars[i]
            close = bar["c"]
            vol_sma = indicators.volume_sma(bars, i, window=20)
            if vol_sma is None or vol_sma == 0:
                continue
            vol_confirmed = bar["v"] > VOLUME_CONFIRMATION_MULTIPLE * vol_sma
            above_vwap = close > vwap[i]["vwap"]
            below_vwap = close < vwap[i]["vwap"]

            bullish = close > orb["high"] * (1 + BREAKOUT_THRESHOLD_PCT) and vol_confirmed and above_vwap
            bearish = close < orb["low"] * (1 - BREAKOUT_THRESHOLD_PCT) and vol_confirmed and below_vwap
            if not (bullish or bearish):
                continue

            right = "C" if bullish else "P"
            long_target = close  # ATM
            short_target = close + SPREAD_WIDTH if bullish else close - SPREAD_WIDTH
            built = common.build_vertical_spread(day, right, long_target, short_target)
            if not built:
                continue
            entry_time = bar["t"]
            entry_debit = common.price_vertical_at(built["bars"], entry_time)
            if entry_debit is None or entry_debit <= 0:
                continue
            max_loss = entry_debit
            contracts = common.size_position(max_loss)
            if contracts < 1:
                continue

            all_times = [b["t"] for b in bars]
            trade = common.simulate_debit_spread(
                day, "orb_breakout", built, entry_time, entry_debit, contracts, all_times,
                PROFIT_TAKE_PCT, STOP_LOSS_PCT,
            )
            trade_dict = trade.__dict__
            trade_dict["meta"] = {"direction": "bullish" if bullish else "bearish", "orb_range_pct": orb["range_pct"]}
            trades.append(trade_dict)
            entered = True
            break  # one entry per day for this strategy - first valid breakout wins

        if not entered:
            skipped.append({"day": day.isoformat(), "reason": "no_breakout_confirmed"})

    return {"strategy": "orb_breakout", "trades": trades, "skipped": skipped}
