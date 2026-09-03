"""CLI wrapper so the tuning search can score a candidate parameter set without writing throwaway
Python each iteration. Missing keys in the params JSON fall back to strategy_1_iron_condor's own
defaults (see strategy_1_iron_condor.run()'s `params` argument).

Usage:
  python -m backtest.tuning.run_eval '{"target_delta": 0.14}' train
  python -m backtest.tuning.run_eval '{"target_delta": 0.14}' test
"""
import sys
import json

from . import evaluator, split as split_module


def main():
    params = json.loads(sys.argv[1])
    split_name = sys.argv[2] if len(sys.argv) > 2 else "train"

    train_days, test_days = split_module.train_test_split()
    days = train_days if split_name == "train" else test_days

    score = evaluator.evaluate(params, days)
    print(json.dumps(score, indent=2))


if __name__ == "__main__":
    main()
