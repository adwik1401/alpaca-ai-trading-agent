"""One full agent cycle. Meant to be run on a schedule (GitHub Actions cron, Phase 2 Step 8).
Order of operations, every run:
  1. Circuit breakers first - a kill switch always wins, regardless of anything else.
  2. Manage any existing position (profit-take / stop-loss / 0-DTE close).
  3. Only if flat and not halted: evaluate a new entry.
Every branch writes to the audit log, including "nothing happened" runs - the log is the
evidence trail for judging, not just a debug aid.
"""
import sys

from . import config, governor, risk_gates, analyst, executor, audit_log


def get_open_spy_option_positions() -> list[dict]:
    positions = executor.list_positions()
    return [p for p in positions if p.get("symbol", "").startswith(config.UNDERLYING) and p.get("asset_class") == "us_option"]


def manage_existing_position(positions: list[dict]) -> bool:
    """Returns True if a management action was taken (so the caller skips entry logic this run)."""
    if not positions:
        return False

    expiry_from_symbol = positions[0]["symbol"][3:9]  # YYMMDD right after the ticker
    expiry_iso = f"20{expiry_from_symbol[0:2]}-{expiry_from_symbol[2:4]}-{expiry_from_symbol[4:6]}"

    if risk_gates.is_past_zero_dte_cutoff(expiry_iso):
        audit_log.log("zero_dte_liquidation", {"expiry": expiry_iso, "positions": len(positions)})
        executor.cancel_all_orders()
        result = executor.liquidate_all()
        audit_log.log("liquidation_result", {"result": result})
        return True

    total_entry_credit = 0.0
    total_current_value = 0.0
    for p in positions:
        qty = float(p["qty"])
        avg_entry = float(p["avg_entry_price"])
        current_price = float(p.get("current_price") or avg_entry)
        side_sign = -1 if p.get("side") == "short" else 1
        total_entry_credit += -side_sign * avg_entry * abs(qty) * 100
        total_current_value += -side_sign * current_price * abs(qty) * 100

    if total_entry_credit <= 0:
        audit_log.log("position_check_skipped", {"reason": "not_a_net_credit_position", "positions": len(positions)})
        return False

    captured_pct = (total_entry_credit - total_current_value) / total_entry_credit
    loss_multiple = (total_current_value - total_entry_credit) / total_entry_credit if total_current_value > total_entry_credit else 0

    audit_log.log("position_status", {
        "expiry": expiry_iso, "entry_credit": total_entry_credit, "current_value": total_current_value,
        "captured_pct": captured_pct, "loss_multiple": loss_multiple,
    })

    if captured_pct >= config.PROFIT_TAKE_PCT:
        audit_log.log("exit_triggered", {"reason": "profit_take_50pct", "captured_pct": captured_pct})
        executor.cancel_all_orders()
        executor.liquidate_all()
        return True

    if loss_multiple >= config.STOP_LOSS_MULTIPLE:
        audit_log.log("exit_triggered", {"reason": "stop_loss_2x_credit", "loss_multiple": loss_multiple})
        executor.cancel_all_orders()
        executor.liquidate_all()
        return True

    return True  # holding - still counts as "handled" for this run


def evaluate_new_entry() -> None:
    signal = governor.build_live_condor_signal()
    debate = analyst.run_debate(signal) if signal.get("expiry") else None

    audit_log.log("entry_evaluation", {
        "signal": {k: v for k, v in signal.items() if k != "plan"},
        "analyst_debate": debate,
    })

    if not signal.get("tradeable") or not signal.get("plan"):
        audit_log.log("entry_skipped", {"reason": signal.get("reason", "gates_not_met")})
        return

    account = risk_gates.get_account()
    contracts = risk_gates.size_position(signal["max_loss_per_contract"], account)
    if contracts < 1:
        audit_log.log("entry_skipped", {"reason": "position_size_zero", "max_loss_per_contract": signal["max_loss_per_contract"]})
        return

    plan = signal["plan"]
    plan.contracts = contracts
    result = executor.submit_condor_open(plan)
    audit_log.log("entry_submitted", {
        "plan": plan.model_dump(), "order_result": result,
        "analyst_recommendation": debate.get("recommendation") if debate else None,
    })


def main():
    breaker_state = risk_gates.check_circuit_breakers()
    audit_log.log("circuit_breaker_check", breaker_state)

    if breaker_state["action"] == "kill_switch":
        audit_log.log("kill_switch_triggered", breaker_state)
        executor.cancel_all_orders()
        result = executor.liquidate_all()
        audit_log.log("liquidation_result", {"result": result})
        return

    positions = get_open_spy_option_positions()
    handled = manage_existing_position(positions)
    if handled:
        return

    if breaker_state["action"] == "halt_new_entries":
        audit_log.log("entry_halted", {"reason": "intraday_drawdown_breaker", **breaker_state})
        return

    evaluate_new_entry()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        audit_log.log("agent_error", {"error": str(e), "type": type(e).__name__})
        sys.exit(1)
