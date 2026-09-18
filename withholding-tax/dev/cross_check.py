"""Cross-checks rule_engine.py against rule_engine2.py on generated
scenarios -- they must agree exactly (to the cent) on every payment's
final_withholding_usd, true_up_usd, and the grand total. A mismatch
means one of the two independently-coded implementations has a bug that
would otherwise silently define the pass bar.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scenario_gen import generate_scenario, write_scenario  # noqa: E402
import rule_engine as eng1  # noqa: E402
import rule_engine2 as eng2  # noqa: E402


def check(label, out_dir, **gen_kwargs):
    b = generate_scenario(**gen_kwargs)
    write_scenario(b, out_dir, fx_seed=gen_kwargs["seed"])
    sc = eng1.load_scenario(out_dir)
    r1 = eng1.compute_report(sc)
    r2 = eng2.load_and_compute(out_dir)

    ok = True
    if r1["total_liability_usd"] != r2["total_liability_usd"]:
        ok = False
        print(f"  TOTAL MISMATCH: eng1={r1['total_liability_usd']} eng2={r2['total_liability_usd']}")

    by_id1 = {ln["payment_id"]: ln for ln in r1["payments"]}
    by_id2 = {ln["payment_id"]: ln for ln in r2["payments"]}
    if set(by_id1) != set(by_id2):
        ok = False
        print("  PAYMENT SET MISMATCH")
    for pid in by_id1:
        l1, l2 = by_id1[pid], by_id2[pid]
        for field in ("final_withholding_usd", "true_up_usd"):
            if l1[field] != l2[field]:
                ok = False
                print(f"  {pid}.{field} MISMATCH: eng1={l1[field]} eng2={l2[field]}")

    print(f"{label}: {'MATCH' if ok else 'MISMATCH'} (total={r1['total_liability_usd']}, {len(r1['payments'])} payments)")
    return ok


if __name__ == "__main__":
    profiles = [
        ("sample_A", dict(seed=11, n_threshold_gadgets=1, n_ownership_gadgets=1, n_filler=4)),
        ("sample_B", dict(seed=22, n_threshold_gadgets=2, n_ownership_gadgets=1, n_filler=6)),
        ("sample_C", dict(seed=33, n_threshold_gadgets=1, n_ownership_gadgets=2, n_filler=5)),
        ("held_out_1", dict(seed=44, n_threshold_gadgets=2, n_ownership_gadgets=2, n_filler=6)),
        ("held_out_2", dict(seed=55, n_threshold_gadgets=3, n_ownership_gadgets=2, n_filler=8)),
    ]
    all_ok = True
    for label, kwargs in profiles:
        out_dir = f"/tmp/wt_check_{label}"
        all_ok &= check(label, out_dir, **kwargs)
    print("\nALL MATCH" if all_ok else "\nFAILURES PRESENT")
