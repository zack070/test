#!/usr/bin/env python3
"""Reference solution entry point: loads environment/data/case (as seen
from the agent's own /app working directory) and writes the computed
reconciliation report to /app/outputs/report.json, using the rule engine
in compute_lib.py (byte-identical to dev/rule_engine.py -- see that
file's docstring for the authoritative rule text this implements)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute_lib as eng

DATA_DIR = "/app/data/case"
OUT_PATH = "/app/outputs/report.json"


def main():
    sc = eng.load_scenario(DATA_DIR)
    report = eng.compute_report(sc)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"wrote {OUT_PATH}: total_liability_usd={report['total_liability_usd']}")


if __name__ == "__main__":
    main()
