"""Bounded search space for the 0DTE Iron Condor tuning loop. Bounds and step sizes are drawn
from the research bands already documented as comments in strategy_1_iron_condor.py, not invented
fresh - the search explores around the strategy's own research-backed starting point rather than
an arbitrary range."""
from backtest.intraday import strategy_1_iron_condor as strat

# Each entry: baseline (the strategy file's current constant), min/max (hard bounds - a
# perturbation is clamped to these, never proposed outside them), step (the increment size used
# when proposing a candidate value for this parameter).
PARAMS = {
    "target_delta": {"baseline": strat.TARGET_DELTA, "min": 0.08, "max": 0.20, "step": 0.02},
    "wing_width": {"baseline": strat.WING_WIDTH, "min": 0.5, "max": 3.0, "step": 0.25},
    "calm_range_pct_max": {"baseline": strat.CALM_RANGE_PCT_MAX, "min": 0.003, "max": 0.010, "step": 0.001},
    "calm_vwap_slope_max": {"baseline": strat.CALM_VWAP_SLOPE_MAX, "min": 0.0001, "max": 0.0005, "step": 0.00005},
    "profit_take_pct": {"baseline": strat.PROFIT_TAKE_PCT, "min": 0.3, "max": 0.8, "step": 0.05},
    "stop_loss_multiple": {"baseline": strat.STOP_LOSS_MULTIPLE, "min": 1.25, "max": 2.5, "step": 0.25},
}


def baseline_params() -> dict:
    return {name: spec["baseline"] for name, spec in PARAMS.items()}


def clamp(name: str, value: float) -> float:
    spec = PARAMS[name]
    return round(max(spec["min"], min(spec["max"], value)), 6)
