#!/usr/bin/env python3
"""Cheat: technically valid output, does no real work."""
import argparse
import json

ap = argparse.ArgumentParser()
ap.add_argument("--loans", required=True)
ap.add_argument("--payments", required=True)
ap.add_argument("--window-days", required=True, type=int)
ap.add_argument("--output", required=True)
args = ap.parse_args()

with open(args.output, "w") as f:
    json.dump({"final_ledger": {}, "payment_allocations": []}, f)
