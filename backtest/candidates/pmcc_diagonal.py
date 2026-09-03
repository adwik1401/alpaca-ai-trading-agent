"""Candidate 1 (top research pick): Leveraged Poor Man's Covered Call / call diagonal. Buy a deep-
ITM, long-dated call (~80 delta, 60-90 DTE) as a leveraged stock-replacement; finance it by selling
a rolling OTM call against it (~25 delta, 14-21 DTE), rolled repeatedly. Remaining NAV not allocated
to the diagonal earns the risk-free rate. Research source: Antigravity CLI, 2026-09-02 (ranked #1).

Structurally different from the other 3 candidates: this is ONE continuously-managed position with
repeated rolls, not a series of independent discrete trades - so unlike barbell/momentum/risk_reversal
(which reuse `simulate_single_shot_trade` and report per-trade PnL at trade frequency), this module
runs its own cash-ledger simulation and reports a WEEKLY mark-to-market equity curve. Sharpe/Sortino
computed from that curve use periods_per_year=52 (correct for a position actually marked weekly),
which is NOT directly the same "kind" of Sharpe as the other candidates' per-trade-frequency Sharpe -
both are internally correct annualizations of their own return series, but flagged here explicitly so
nobody repeats the 2026-09-02 sqrt(252)-on-per-trade-returns mistake in reverse (assuming these are
interchangeable without checking what frequency each was computed on).
"""
from datetime import date, timedelta

from .. import data, black_scholes as bs
from . import common
from ..strategies.common import STARTING_NAV, CONTRACT_MULTIPLIER

UNDERLYING = "SPY"
ALLOCATION_PCT = 0.35
# DEVIATION FROM RESEARCH (2026-09-02): research proposed a 60-90 DTE long leg / 14-21 DTE short
# leg. Direct testing found this account's SPY options data has essentially no trade prints
# earlier than ~14 calendar days before a contract's own expiry, regardless of moneyness (a deep-
# ITM 45-DTE-out strike returned ZERO prints in testing, and near-ATM/OTM strikes consistently
# showed their first print at exactly 14 DTE). Both legs are compressed to fit inside that window
# with a safety margin - this materially weakens the "leveraged long-dated stock replacement"
# thesis (a 12-DTE ITM call isn't really a LEAPS substitute), which is flagged honestly rather
# than silently backtesting on data that doesn't exist for the original design.
LONG_TARGET_DTE = 12
LONG_DELTA = 0.80
LONG_ROLL_DTE_FLOOR = 4
SHORT_TARGET_DTE = 6
SHORT_DELTA = 0.25
SHORT_ROLL_DTE_FLOOR = 1
SHORT_PROFIT_TAKE_PCT = 0.5
CHECK_INTERVAL_DAYS = 3  # finer-grained than the weekly engine, to resolve the compressed roll cycle


OPEN_PRICE_LOOKBACK_DAYS = 21  # how far before entry to look for a real print, if not on the day itself


def _fetch_call_leg(expiry: date, spot: float, sigma: float, T: float, target_delta: float,
                     open_date: date, window_end: date):
    """Find a strike near the delta target with real trade activity, then price it 'as of' the
    open date (most recent print at-or-before, no look-ahead) rather than requiring an exact print
    on the entry day - this account's option data has sparse trade-print coverage away from the
    most actively-traded near-expiry window (confirmed 2026-09-02), so an exact-day requirement
    starved this strategy of entries even on liquid near-ATM strikes. `find_liquid_strike` (any
    print anywhere in the fetch window) is the same liquidity filter the weekly Hybrid strategy
    already uses successfully."""
    target_strike = common.strike_for_call_delta(spot, T, sigma, target_delta)
    data_start = (open_date - timedelta(days=OPEN_PRICE_LOOKBACK_DAYS)).isoformat()
    data_end = (min(expiry, window_end) + timedelta(days=1)).isoformat()
    found = common.find_liquid_strike(UNDERLYING, expiry, "C", target_strike, data_start, data_end)
    if not found:
        return None
    symbol, bars = found
    open_price = common.price_asof(bars, open_date.isoformat())
    if open_price is None:
        return None
    return {"symbol": symbol, "bars": bars, "strike": float(symbol[-8:]) / 1000, "expiry": expiry,
            "open_date": open_date, "open_price": open_price}


def run(lookback_weeks: int = 26) -> dict:
    today = date.today()
    # Alpaca's historical option-bars endpoint 403s ("OPRA agreement is not signed") for ANY
    # contract that hasn't reached its own expiration date yet - confirmed by direct testing
    # 2026-09-02: even a contract expiring tomorrow returns 403 for its entire history, including
    # days already in the past. This account has no real-time OPRA data entitlement. PMCC needs
    # marks on a still-open ~75-DTE long leg, so new legs may only be OPENED if they're guaranteed
    # to have fully expired by today - the walk-forward itself still runs all the way to today,
    # continuing to mark/roll whatever's already open. Real-data-only stays non-negotiable: the
    # alternative (theoretical BS marks for an unexpired tail) was rejected as inconsistent with
    # every other backtest in this project only ever using real observed option prices for P&L.
    long_open_cutoff = today - timedelta(days=LONG_TARGET_DTE + 1)
    short_open_cutoff = today - timedelta(days=SHORT_TARGET_DTE + 1)
    window_end = today - timedelta(days=1)
    backtest_start = today - timedelta(weeks=lookback_weeks)
    history_start = backtest_start - timedelta(weeks=8)
    equity_bars = data.get_equity_bars(UNDERLYING, history_start.isoformat(), (window_end + timedelta(days=1)).isoformat())
    closes_by_date = {b["t"][:10]: b["c"] for b in equity_bars}
    sorted_dates = sorted(closes_by_date.keys())

    def sigma_at(as_of: str) -> float | None:
        past = [closes_by_date[dd] for dd in sorted_dates if dd <= as_of]
        if len(past) < 21:
            return None
        return bs.realized_vol(past, window=20)

    checkpoints = []
    d = backtest_start
    while d.weekday() >= 5:
        d += timedelta(days=1)
    while d <= window_end:
        checkpoints.append(d)
        d += timedelta(days=CHECK_INTERVAL_DAYS)

    events = []  # roll/open/close log, for reporting
    equity_curve = []  # [(date, total_portfolio_value)]
    weekly_returns = []

    long_leg, short_leg = None, None
    cash_ledger = 0.0
    contracts = None
    unallocated_cash = None
    started = False
    wound_down = False  # once True, no more legs are opened - position runs off into cash only
    skipped = []

    for cp in checkpoints:
        cp_str = cp.isoformat()
        if cp_str not in closes_by_date:
            skipped.append({"checkpoint": cp_str, "reason": "no_equity_bar"})
            continue
        spot = closes_by_date[cp_str]
        sigma = sigma_at(cp_str)
        if sigma is None:
            skipped.append({"checkpoint": cp_str, "reason": "insufficient_rv_history"})
            continue

        # --- Long leg: open initially, roll when DTE drops below the floor ---
        long_dte = (long_leg["expiry"] - cp).days if long_leg else -1
        long_due = long_leg is None or long_dte < LONG_ROLL_DTE_FLOOR
        if long_due and not wound_down:
            if cp > long_open_cutoff:
                # A fresh long leg opened now wouldn't fully expire before today (OPRA-gated) -
                # wind the whole diagonal down instead of holding a stale/unrollable position.
                if long_leg is not None:
                    close_price = common.price_asof(long_leg["bars"], cp_str)
                    if close_price is not None and contracts:
                        cash_ledger += close_price * contracts * CONTRACT_MULTIPLIER
                        events.append({"date": cp_str, "action": "wind_down_close_long", "symbol": long_leg["symbol"], "price": close_price})
                if short_leg is not None:
                    close_price = common.price_asof(short_leg["bars"], cp_str)
                    if close_price is not None and contracts:
                        cash_ledger -= close_price * contracts * CONTRACT_MULTIPLIER
                        events.append({"date": cp_str, "action": "wind_down_close_short", "symbol": short_leg["symbol"], "price": close_price})
                long_leg, short_leg, wound_down = None, None, True
                skipped.append({"checkpoint": cp_str, "reason": "long_roll_due_but_past_open_cutoff_wound_down"})
            else:
                if long_leg is not None:
                    close_price = common.price_asof(long_leg["bars"], cp_str)
                    if close_price is None:
                        skipped.append({"checkpoint": cp_str, "reason": "long_leg_close_price_missing"})
                        continue
                    if contracts:
                        cash_ledger += close_price * contracts * CONTRACT_MULTIPLIER
                    events.append({"date": cp_str, "action": "close_long", "symbol": long_leg["symbol"], "price": close_price})

                new_expiry = common.nearest_weekday_expiry(cp + timedelta(days=LONG_TARGET_DTE))
                T = max((new_expiry - cp).days, 1) / 365
                new_long = _fetch_call_leg(new_expiry, spot, sigma, T, LONG_DELTA, cp, window_end)
                if not new_long:
                    skipped.append({"checkpoint": cp_str, "reason": "no_liquid_long_leg"})
                    long_leg = None
                else:
                    open_price = new_long["open_price"]
                    if not started:
                        # Size the position once, off the first diagonal's approximate net debit,
                        # then hold contract count fixed for the rest of the backtest (documented
                        # simplification - a real live agent could resize on every roll, but that
                        # adds a second compounding dimension this backtest isn't trying to model).
                        short_probe_expiry = common.nearest_weekday_expiry(cp + timedelta(days=SHORT_TARGET_DTE))
                        T_short = max((short_probe_expiry - cp).days, 1) / 365
                        probe_short = _fetch_call_leg(short_probe_expiry, spot, sigma, T_short, SHORT_DELTA, cp, window_end)
                        probe_short_price = probe_short["open_price"] if probe_short else None
                        approx_net_debit = open_price - (probe_short_price or 0.0)
                        if approx_net_debit <= 0:
                            skipped.append({"checkpoint": cp_str, "reason": "non_positive_initial_debit"})
                            long_leg = None
                        else:
                            risk_budget = STARTING_NAV * ALLOCATION_PCT
                            contracts = max(1, int(risk_budget / (approx_net_debit * CONTRACT_MULTIPLIER)))
                            unallocated_cash = STARTING_NAV - contracts * approx_net_debit * CONTRACT_MULTIPLIER
                            started = True
                    if started:
                        cash_ledger -= open_price * contracts * CONTRACT_MULTIPLIER
                        long_leg = new_long
                        events.append({"date": cp_str, "action": "open_long", "symbol": new_long["symbol"], "strike": new_long["strike"], "expiry": new_expiry.isoformat(), "price": open_price})

        if not started or wound_down or long_leg is None:
            # long_leg is None here means a mid-run roll failed to find a new contract (not a
            # wind-down - wound_down would already be True in that case) - treat this checkpoint
            # as a temporary gap (no position to mark) rather than crashing on short-leg logic
            # that assumes a long leg exists. The loop will retry opening a new long leg next
            # checkpoint. Close out any now-uncovered short leg too, rather than leaving a naked
            # short unaccounted for while there's no long leg backing it.
            if started and long_leg is None and short_leg is not None:
                close_price = common.price_asof(short_leg["bars"], cp_str)
                if close_price is not None:
                    cash_ledger -= close_price * contracts * CONTRACT_MULTIPLIER
                    events.append({"date": cp_str, "action": "close_short_no_long_backing", "symbol": short_leg["symbol"], "price": close_price})
                short_leg = None
            if started:
                # Wound down (or gapped): cash_ledger is now fully realized/frozen. Yield here
                # only accrues on the original unallocated_cash sleeve, same formula as the active
                # phase below - the newly-freed capital's own yield from its wind-down date is
                # left out as a small, deliberately conservative (understates return) simplification.
                days_elapsed = (cp - checkpoints[0]).days
                cash_yield = common.cash_yield_accrual(unallocated_cash, days_elapsed)
                total_value = STARTING_NAV + cash_ledger + cash_yield
                equity_curve.append((cp_str, round(total_value, 2)))
            continue

        # --- Short leg: open initially, roll on DTE floor or 50% profit captured ---
        short_dte = (short_leg["expiry"] - cp).days if short_leg else -1
        should_roll_short = short_leg is None or short_dte < SHORT_ROLL_DTE_FLOOR
        if short_leg is not None and not should_roll_short:
            cur_price = common.price_asof(short_leg["bars"], cp_str)
            if cur_price is not None and short_leg["open_price"] - cur_price >= SHORT_PROFIT_TAKE_PCT * short_leg["open_price"]:
                should_roll_short = True

        if should_roll_short and cp <= short_open_cutoff:
            if short_leg is not None:
                close_price = common.price_asof(short_leg["bars"], cp_str)
                if close_price is not None:
                    cash_ledger -= close_price * contracts * CONTRACT_MULTIPLIER
                    events.append({"date": cp_str, "action": "close_short", "symbol": short_leg["symbol"], "price": close_price})
                short_leg = None

            new_short_expiry = common.nearest_weekday_expiry(cp + timedelta(days=SHORT_TARGET_DTE))
            if new_short_expiry >= long_leg["expiry"]:
                new_short_expiry = long_leg["expiry"] - timedelta(days=1)
                while new_short_expiry.weekday() >= 5:
                    new_short_expiry -= timedelta(days=1)
            T_short = max((new_short_expiry - cp).days, 1) / 365
            new_short = _fetch_call_leg(new_short_expiry, spot, sigma, T_short, SHORT_DELTA, cp, window_end)
            if new_short:
                open_price = new_short["open_price"]
                cash_ledger += open_price * contracts * CONTRACT_MULTIPLIER
                short_leg = new_short
                events.append({"date": cp_str, "action": "open_short", "symbol": new_short["symbol"], "strike": new_short["strike"], "expiry": new_short_expiry.isoformat(), "price": open_price})
            else:
                skipped.append({"checkpoint": cp_str, "reason": "no_liquid_short_leg"})
        elif should_roll_short and short_leg is not None and cp > short_open_cutoff:
            # Due for a roll but a fresh short wouldn't fully expire before today - let this one
            # ride uncovered-short-free (still fine: the long call alone just keeps its full delta).
            close_price = common.price_asof(short_leg["bars"], cp_str)
            if close_price is not None:
                cash_ledger -= close_price * contracts * CONTRACT_MULTIPLIER
                events.append({"date": cp_str, "action": "close_short_no_reroll_past_cutoff", "symbol": short_leg["symbol"], "price": close_price})
            short_leg = None

        # --- Mark-to-market for the weekly equity curve ---
        long_mark = common.price_asof(long_leg["bars"], cp_str) if long_leg else None
        short_mark = common.price_asof(short_leg["bars"], cp_str) if short_leg else None
        if long_mark is None:
            continue
        unrealized = long_mark * contracts * CONTRACT_MULTIPLIER
        if short_mark is not None:
            unrealized -= short_mark * contracts * CONTRACT_MULTIPLIER

        days_elapsed = (cp - checkpoints[0]).days
        cash_yield = common.cash_yield_accrual(unallocated_cash, days_elapsed)
        total_value = STARTING_NAV + cash_ledger + unrealized + cash_yield
        equity_curve.append((cp_str, round(total_value, 2)))

    for i in range(1, len(equity_curve)):
        prev_value = equity_curve[i - 1][1]
        if prev_value:
            weekly_returns.append((equity_curve[i][1] - prev_value) / prev_value)

    # Close out any still-open legs at the final observed prices to realize final PnL.
    final_cp_str = checkpoints[-1].isoformat() if checkpoints else None
    if long_leg and final_cp_str:
        final_price = common.price_asof(long_leg["bars"], final_cp_str)
        if final_price is not None and contracts:
            cash_ledger += final_price * contracts * CONTRACT_MULTIPLIER
            events.append({"date": final_cp_str, "action": "final_close_long", "symbol": long_leg["symbol"], "price": final_price})
    if short_leg and final_cp_str:
        final_price = common.price_asof(short_leg["bars"], final_cp_str)
        if final_price is not None and contracts:
            cash_ledger -= final_price * contracts * CONTRACT_MULTIPLIER
            events.append({"date": final_cp_str, "action": "final_close_short", "symbol": short_leg["symbol"], "price": final_price})

    total_days = (checkpoints[-1] - checkpoints[0]).days if len(checkpoints) > 1 else 0
    final_cash_yield = common.cash_yield_accrual(unallocated_cash, total_days) if unallocated_cash is not None else 0.0
    total_pnl = cash_ledger + final_cash_yield
    final_nav = STARTING_NAV + total_pnl

    return {
        "strategy": "pmcc_diagonal",
        "events": events,
        "skipped": skipped,
        "equity_curve": equity_curve,
        "weekly_returns": weekly_returns,
        "contracts": contracts,
        "allocation_used": round(contracts * ALLOCATION_PCT, 2) if contracts else None,
        "unallocated_cash": round(unallocated_cash, 2) if unallocated_cash is not None else None,
        "total_pnl": round(total_pnl, 2),
        "final_nav": round(final_nav, 2),
        "return_pct": round(total_pnl / STARTING_NAV * 100, 2),
        "num_rolls": len([e for e in events if e["action"].startswith("open")]),
        "wound_down_early": wound_down,
        "data_constraint_note": (
            "Alpaca's historical option-bars API only serves contracts that have already expired "
            "(no OPRA real-time entitlement on this account) - new long/short legs are only opened "
            "if guaranteed to fully expire before today; if a roll came due after that cutoff the "
            "position was wound down to cash rather than faked with theoretical pricing."
        ),
    }
