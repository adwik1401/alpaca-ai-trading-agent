"""Executor layer: takes a validated order plan and submits it via the Alpaca CLI as an atomic
MLEG order. This is the ONLY layer allowed to touch the broker - never call the REST API
directly for order placement, so the "MCP or CLI" hackathon requirement is met by construction.

CLI syntax verified live against the dev paper account on 2026-09-02 (see agent-log.md):
`alpaca order submit --order-class mleg --type limit --limit-price <net> --time-in-force day
--qty <n> --legs '[{"symbol":...,"side":"sell"|"buy","ratio_qty":"1"}, ...]'`
"""
import json
import subprocess

from pydantic import BaseModel, field_validator

from . import config


class OrderLeg(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    ratio_qty: str = "1"

    @field_validator("side")
    @classmethod
    def side_must_be_valid(cls, v):
        if v not in ("buy", "sell"):
            raise ValueError(f"invalid side: {v}")
        return v

    @field_validator("symbol")
    @classmethod
    def symbol_must_be_osi(cls, v):
        # TICKER + YYMMDD + C/P + 8-digit strike, e.g. SPY260904C00770000
        if len(v) < 15 or v[-9] not in ("C", "P") or not v[-8:].isdigit():
            raise ValueError(f"symbol does not look like a valid OSI option symbol: {v}")
        return v


class CondorOrderPlan(BaseModel):
    """The only shape an order can take. Anything not expressible as this schema is rejected
    before it reaches the CLI - the LLM never gets to freeform an order payload."""
    legs: list[OrderLeg]
    limit_price: float  # net credit (positive) for opening an iron condor
    contracts: int

    @field_validator("legs")
    @classmethod
    def must_be_four_legs(cls, v):
        if len(v) != 4:
            raise ValueError(f"iron condor must have exactly 4 legs, got {len(v)}")
        return v

    @field_validator("contracts")
    @classmethod
    def contracts_positive(cls, v):
        if v < 1:
            raise ValueError("contracts must be >= 1")
        return v


class CLIError(RuntimeError):
    pass


def _run_cli(args: list[str]) -> dict:
    env_overrides = {
        "ALPACA_API_KEY": config.ALPACA_API_KEY,
        "ALPACA_SECRET_KEY": config.ALPACA_SECRET_KEY,
    }
    import os

    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        [config.ALPACA_CLI_PATH, *args, "--quiet"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    if result.returncode != 0:
        raise CLIError(f"alpaca CLI failed: {result.stdout} {result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def submit_condor_open(plan: CondorOrderPlan) -> dict:
    """Open a 4-leg iron condor as one atomic order - all legs fill together at the net
    credit limit, or none fill at all."""
    legs_json = json.dumps([leg.model_dump() for leg in plan.legs])
    return _run_cli([
        "order", "submit",
        "--order-class", "mleg",
        "--type", "limit",
        "--limit-price", f"{plan.limit_price:.2f}",
        "--time-in-force", "day",
        "--qty", str(plan.contracts),
        "--legs", legs_json,
    ])


def submit_condor_close(plan: CondorOrderPlan) -> dict:
    """Close an existing condor: same 4 legs, sides flipped, submitted as a debit (or smaller
    credit) limit order to buy back the shorts and sell the longs."""
    closing_legs = [
        OrderLeg(symbol=leg.symbol, side=("buy" if leg.side == "sell" else "sell"), ratio_qty=leg.ratio_qty)
        for leg in plan.legs
    ]
    legs_json = json.dumps([leg.model_dump() for leg in closing_legs])
    return _run_cli([
        "order", "submit",
        "--order-class", "mleg",
        "--type", "limit",
        "--limit-price", f"{plan.limit_price:.2f}",
        "--time-in-force", "day",
        "--qty", str(plan.contracts),
        "--legs", legs_json,
    ])


def cancel_order(order_id: str) -> dict:
    return _run_cli(["order", "cancel", "--order-id", order_id])


def get_account() -> dict:
    return _run_cli(["account", "get"])


def list_open_orders() -> list[dict]:
    result = _run_cli(["order", "list", "--status", "open"])
    return result if isinstance(result, list) else []


def list_positions() -> list[dict]:
    result = _run_cli(["position", "list"])
    return result if isinstance(result, list) else []


def liquidate_all() -> dict:
    """Kill switch: close every open position immediately."""
    return _run_cli(["position", "close-all"])


def cancel_all_orders() -> dict:
    return _run_cli(["order", "cancel-all"])
