#!/usr/bin/env bash
# Local (no-Docker) verification harness. Usage:
#   dev/local_harness.sh <path-to-candidate-poster.py>
# Prints the final reward (0 or 1) and leaves logs under the scratch dir.
set -uo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE_POSTER="$1"
SCRATCH="$(mktemp -d /tmp/lsp_harness.XXXXXX)"

mkdir -p "$SCRATCH/app/outputs" "$SCRATCH/tests" "$SCRATCH/work" "$SCRATCH/logs/verifier"
cp "$CANDIDATE_POSTER" "$SCRATCH/app/outputs/poster.py"
cp -r "$BUNDLE_DIR/tests/." "$SCRATCH/tests/"

sed -i "s#/app/outputs/poster.py#$SCRATCH/app/outputs/poster.py#g; s#/tests/sealed#$SCRATCH/tests/sealed#g; s#/work#$SCRATCH/work#g" "$SCRATCH/tests/collect_agent_output.py"
sed -i "s#/tests/sealed#$SCRATCH/tests/sealed#g; s#/work#$SCRATCH/work#g" "$SCRATCH/tests/test_loanposting_grading.py"
sed -i "s#/tests#$SCRATCH/tests#g; s#/work#$SCRATCH/work#g; s#/logs/verifier#$SCRATCH/logs/verifier#g; s#/app/outputs#$SCRATCH/app/outputs#g" "$SCRATCH/tests/test.sh"

chmod 755 "$SCRATCH"
chown -R runner:runner "$SCRATCH/app" "$SCRATCH/work"
chmod -R o+rX "$SCRATCH/tests"

SYMLINKED=0
if [ "${EXPLOIT_TEST_SYMLINK:-0}" = "1" ]; then
    if [ -e /tests ] || [ -L /tests ]; then
        echo "EXPLOIT_TEST_SYMLINK=1 but /tests already exists -- refusing to touch it" >&2
        exit 1
    fi
    ln -s "$SCRATCH/tests" /tests
    SYMLINKED=1
fi

bash "$SCRATCH/tests/test.sh"

if [ "$SYMLINKED" = "1" ]; then
    rm -f /tests
fi

echo "---- reward ----"
cat "$SCRATCH/logs/verifier/reward.txt"
echo
echo "---- stage1 log ----"
cat "$SCRATCH/work/stage1.log" 2>/dev/null
echo "---- stage2 log (tail) ----"
tail -80 "$SCRATCH/work/stage2.log" 2>/dev/null
echo "---- orphaned runner processes ----"
ps -u runner 2>/dev/null || true
echo "---- scratch dir ----"
echo "$SCRATCH"
