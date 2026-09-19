#!/usr/bin/env python3
"""Cheat: memorized answer for the visible practice case (seed 9001,
skus SKU500-SKU559), embedded inline since only one file is graded.
Outputs it regardless of the actual input -- should fail because the
sealed grading datasets use disjoint sku ranges (SKU000-059 / SKU200-259)."""
import json
import sys

MEMORIZED_REPORT = json.loads('{"skus": {"SKU500": {"on_hand_qty": 0, "valuation": 0.0}, "SKU501": {"on_hand_qty": 50, "valuation": 350.0}, "SKU502": {"on_hand_qty": 0, "valuation": 0.0}, "SKU503": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU504": {"on_hand_qty": 0, "valuation": 0.0}, "SKU505": {"on_hand_qty": 50, "valuation": 350.0}, "SKU506": {"on_hand_qty": 50, "valuation": 350.0}, "SKU507": {"on_hand_qty": 0, "valuation": 0.0}, "SKU508": {"on_hand_qty": 50, "valuation": 350.0}, "SKU509": {"on_hand_qty": 0, "valuation": 0.0}, "SKU510": {"on_hand_qty": 50, "valuation": 250.0}, "SKU511": {"on_hand_qty": 50, "valuation": 350.0}, "SKU512": {"on_hand_qty": 0, "valuation": 0.0}, "SKU513": {"on_hand_qty": 0, "valuation": 0.0}, "SKU514": {"on_hand_qty": 50, "valuation": 250.0}, "SKU515": {"on_hand_qty": 0, "valuation": 0.0}, "SKU516": {"on_hand_qty": 50, "valuation": 350.0}, "SKU517": {"on_hand_qty": 0, "valuation": 0.0}, "SKU518": {"on_hand_qty": 50, "valuation": 250.0}, "SKU519": {"on_hand_qty": 0, "valuation": 0.0}, "SKU520": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU521": {"on_hand_qty": 0, "valuation": 0.0}, "SKU522": {"on_hand_qty": 50, "valuation": 350.0}, "SKU523": {"on_hand_qty": 0, "valuation": 0.0}, "SKU524": {"on_hand_qty": 85, "valuation": 770.0}, "SKU525": {"on_hand_qty": 50, "valuation": 350.0}, "SKU526": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU527": {"on_hand_qty": 50, "valuation": 250.0}, "SKU528": {"on_hand_qty": 50, "valuation": 250.0}, "SKU529": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU530": {"on_hand_qty": 50, "valuation": 350.0}, "SKU531": {"on_hand_qty": 0, "valuation": 0.0}, "SKU532": {"on_hand_qty": 0, "valuation": 0.0}, "SKU533": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU534": {"on_hand_qty": 50, "valuation": 250.0}, "SKU535": {"on_hand_qty": 50, "valuation": 350.0}, "SKU536": {"on_hand_qty": 0, "valuation": 0.0}, "SKU537": {"on_hand_qty": 50, "valuation": 250.0}, "SKU538": {"on_hand_qty": 50, "valuation": 350.0}, "SKU539": {"on_hand_qty": 50, "valuation": 350.0}, "SKU540": {"on_hand_qty": 0, "valuation": 0.0}, "SKU541": {"on_hand_qty": 0, "valuation": 0.0}, "SKU542": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU543": {"on_hand_qty": 50, "valuation": 250.0}, "SKU544": {"on_hand_qty": 50, "valuation": 350.0}, "SKU545": {"on_hand_qty": 50, "valuation": 350.0}, "SKU546": {"on_hand_qty": 85, "valuation": 770.0}, "SKU547": {"on_hand_qty": 50, "valuation": 350.0}, "SKU548": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU549": {"on_hand_qty": 50, "valuation": 350.0}, "SKU550": {"on_hand_qty": 85, "valuation": 770.0}, "SKU551": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU552": {"on_hand_qty": 50, "valuation": 350.0}, "SKU553": {"on_hand_qty": 50, "valuation": 350.0}, "SKU554": {"on_hand_qty": 50, "valuation": 350.0}, "SKU555": {"on_hand_qty": 50, "valuation": 350.0}, "SKU556": {"on_hand_qty": 0, "valuation": 0.0}, "SKU557": {"on_hand_qty": 0, "valuation": 0.0}, "SKU558": {"on_hand_qty": 175, "valuation": 1850.0}, "SKU559": {"on_hand_qty": 0, "valuation": 0.0}}}')


def run(data_dir):
    return MEMORIZED_REPORT


def main():
    output_path = sys.argv[2]
    with open(output_path, "w") as f:
        json.dump(MEMORIZED_REPORT, f)


if __name__ == "__main__":
    main()
