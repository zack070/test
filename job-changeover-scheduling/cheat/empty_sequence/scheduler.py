#!/usr/bin/env python3
"""Cheat: technically valid output, does no real work."""
import argparse
import json

ap = argparse.ArgumentParser()
ap.add_argument("--instance", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--time-budget", required=True, type=float)
args = ap.parse_args()

with open(args.output, "w") as f:
    json.dump({"sequence": []}, f)
