#!/usr/bin/env bash
# Local (no-Docker) verification harness. Usage:
#   dev/local_harness.sh <path-to-candidate-report.json>
# Prints the final reward (0 or 1) and leaves logs under the scratch dir.
set -uo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE_REPORT="$1"
SCRATCH="$(mktemp -d /tmp/wt_harness.XXXXXX)"

mkdir -p "$SCRATCH/app/outputs" "$SCRATCH/tests" "$SCRATCH/logs/verifier"
cp "$CANDIDATE_REPORT" "$SCRATCH/app/outputs/report.json"
cp -r "$BUNDLE_DIR/tests/." "$SCRATCH/tests/"

sed -i "s#/app/outputs/report.json#$SCRATCH/app/outputs/report.json#g" "$SCRATCH/tests/test_withholding_grading.py"
sed -i "s#/tests/sealed#$SCRATCH/tests/sealed#g" "$SCRATCH/tests/test_withholding_grading.py"
sed -i "s#/tests#$SCRATCH/tests#g; s#/logs/verifier#$SCRATCH/logs/verifier#g" "$SCRATCH/tests/test.sh"

bash "$SCRATCH/tests/test.sh"

echo "---- reward ----"
cat "$SCRATCH/logs/verifier/reward.txt"
echo
echo "---- scratch dir ----"
echo "$SCRATCH"
