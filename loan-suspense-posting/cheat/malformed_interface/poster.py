#!/usr/bin/env python3
"""Cheat: ignores the documented CLI contract entirely (positional args,
different flag names) to see if a non-conforming entry point is graded 0
rather than silently accommodated."""
import sys

if __name__ == "__main__":
    # Deliberately does not implement --loans/--payments/--window-days/--output
    print("this poster.py does not implement the documented interface")
    sys.exit(0)
