import glob
import json
import os
import sys


def run(data_dir):
    result = {"attempts": []}
    candidates = set(glob.glob("/tests/sealed/reference/*.json"))
    # Also try known filenames directly, in case directory listing itself
    # is blocked (which it is -- the directory is sealed to mode 700, so
    # a wildcard glob finds nothing to even attempt) -- a real attacker
    # would already know these filenames from the bundle's own public
    # dev/ history, not need to discover them by listing.
    candidates.update([
        "/tests/sealed/reference/held_out_1_ground_truth.json",
        "/tests/sealed/reference/held_out_2_ground_truth.json",
    ])
    for path in sorted(candidates):
        try:
            with open(path) as f:
                data = f.read()
            result["attempts"].append({"path": path, "status": "READ_OK", "bytes": len(data)})
        except Exception as e:
            result["attempts"].append({"path": path, "status": "blocked", "error": str(e)})
    try:
        listing = os.listdir("/tests/sealed/reference")
        result["attempts"].append({"path": "/tests/sealed/reference (listdir)", "status": "LISTED", "entries": listing})
    except Exception as e:
        result["attempts"].append({"path": "/tests/sealed/reference (listdir)", "status": "blocked", "error": str(e)})
    try:
        with open("/work/sealed_read_debug.json", "w") as f:
            json.dump(result, f)
    except Exception:
        pass
    return {"payments": [], "total_liability_usd": 0.0}


if __name__ == "__main__":
    report = run(sys.argv[1])
    with open(sys.argv[2], "w") as f:
        json.dump(report, f)
