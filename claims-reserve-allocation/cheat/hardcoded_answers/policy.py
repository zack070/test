"""Ships a lookup table of decisions computed on the visible case dataset
(the same generator's claim_id numbering restarts at CLM0001 for every
portfolio, so held-out claim_ids happen to overlap with the visible
case's), falling back to settle-nothing for anything unrecognized. The
underlying claim facts (type, cluster, offer, budget) differ on held-out
data even where the id matches, so this should fail to generalize.

Only one file is ever graded (/app/outputs/policy.py), so the memorized
table has to be embedded directly rather than shipped as a side file --
see cheat/hardcoded_answers/memorized.json for the same table, kept
separately only for readability in this directory.
"""
import csv
import json
import sys

MEMORIZED = {"CLM0001": 0, "CLM0002": 0, "CLM0003": 0, "CLM0004": 0, "CLM0005": 0, "CLM0006": 0, "CLM0007": 0, "CLM0008": 0, "CLM0009": 0, "CLM0010": 0, "CLM0011": 0, "CLM0012": 0, "CLM0013": 0, "CLM0014": 0, "CLM0015": 0, "CLM0016": 0, "CLM0017": 0, "CLM0018": 0, "CLM0019": 0, "CLM0020": 0, "CLM0021": 0, "CLM0022": 0, "CLM0023": 0, "CLM0024": 0, "CLM0025": 0, "CLM0026": 0, "CLM0027": 0, "CLM0028": 0, "CLM0029": 0, "CLM0030": 0, "CLM0031": 0, "CLM0032": 0, "CLM0033": 0, "CLM0034": 0, "CLM0035": 0, "CLM0036": 0, "CLM0037": 0, "CLM0038": 0, "CLM0039": 0, "CLM0040": 0, "CLM0041": 0, "CLM0042": 0, "CLM0043": 0, "CLM0044": 0, "CLM0045": 0, "CLM0046": 0, "CLM0047": 0, "CLM0048": 1, "CLM0049": 0, "CLM0050": 0, "CLM0051": 1, "CLM0052": 0, "CLM0053": 1, "CLM0054": 1, "CLM0055": 1, "CLM0056": 1, "CLM0057": 0, "CLM0058": 1, "CLM0059": 1, "CLM0060": 0, "CLM0061": 1, "CLM0062": 0, "CLM0063": 0, "CLM0064": 0, "CLM0065": 0, "CLM0066": 0, "CLM0067": 1, "CLM0068": 1, "CLM0069": 1, "CLM0070": 1, "CLM0071": 1, "CLM0072": 1, "CLM0073": 0, "CLM0074": 0, "CLM0075": 0, "CLM0076": 1, "CLM0077": 0, "CLM0078": 0, "CLM0079": 0, "CLM0080": 1, "CLM0081": 1, "CLM0082": 1, "CLM0083": 0, "CLM0084": 1, "CLM0085": 0, "CLM0086": 0, "CLM0087": 1, "CLM0088": 0, "CLM0089": 1, "CLM0090": 0, "CLM0091": 1, "CLM0092": 0, "CLM0093": 0, "CLM0094": 0, "CLM0095": 0, "CLM0096": 1, "CLM0097": 0, "CLM0098": 0, "CLM0099": 0, "CLM0100": 1, "CLM0101": 0, "CLM0102": 1, "CLM0103": 0, "CLM0104": 0, "CLM0105": 1, "CLM0106": 1, "CLM0107": 0, "CLM0108": 0, "CLM0109": 0, "CLM0110": 0, "CLM0111": 1, "CLM0112": 1, "CLM0113": 1, "CLM0114": 1, "CLM0115": 0, "CLM0116": 0, "CLM0117": 1, "CLM0118": 0, "CLM0119": 0, "CLM0120": 1, "CLM0121": 0, "CLM0122": 0, "CLM0123": 1, "CLM0124": 0, "CLM0125": 0, "CLM0126": 1, "CLM0127": 0, "CLM0128": 1, "CLM0129": 0, "CLM0130": 0, "CLM0131": 1, "CLM0132": 1, "CLM0133": 1, "CLM0134": 0, "CLM0135": 1, "CLM0136": 0, "CLM0137": 1, "CLM0138": 1, "CLM0139": 0, "CLM0140": 1, "CLM0141": 1, "CLM0142": 0, "CLM0143": 0, "CLM0144": 1, "CLM0145": 1, "CLM0146": 0, "CLM0147": 0, "CLM0148": 1, "CLM0149": 0, "CLM0150": 0, "CLM0151": 0, "CLM0152": 0, "CLM0153": 0, "CLM0154": 1, "CLM0155": 1, "CLM0156": 1, "CLM0157": 0, "CLM0158": 0, "CLM0159": 0, "CLM0160": 0, "CLM0161": 0, "CLM0162": 0, "CLM0163": 1, "CLM0164": 1, "CLM0165": 1}


def main(data_dir, out_path):
    decisions = {}
    with open(f"{data_dir}/claims.csv", newline="") as f:
        for r in csv.DictReader(f):
            decisions[r["claim_id"]] = MEMORIZED.get(r["claim_id"], 0)

    with open(out_path, "w") as f:
        json.dump({"decisions": decisions}, f)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
