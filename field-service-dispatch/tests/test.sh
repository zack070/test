#!/usr/bin/env bash
# Verifier entry point. Runs as root. Never uses set -e: every path,
# including a crash or timeout in either stage, must still reach the
# point where reward.txt gets written.

REWARD_DIR=/logs/verifier
REWARD_FILE="$REWARD_DIR/reward.txt"
WORK_DIR=/work
CTRF_FILE="$REWARD_DIR/ctrf.json"

mkdir -p "$REWARD_DIR" "$WORK_DIR"
chown root:root "$REWARD_DIR"
chmod 700 "$REWARD_DIR"

# Seal the hidden reference data before stage 1 (untrusted) ever runs.
chown -R root:root /tests/sealed/reference
chmod 700 /tests/sealed/reference
find /tests/sealed/reference -type f -exec chmod 600 {} \;
find /tests/sealed/reference -type d -exec chmod 700 {} \;

chown runner:runner "$WORK_DIR"
chmod 700 "$WORK_DIR"

write_reward() {
  echo -n "$1" > "$REWARD_FILE"
  chown root:root "$REWARD_FILE"
  chmod 600 "$REWARD_FILE"
}

# --- Stage 1: untrusted. Executes the candidate's policy code, isolated
# as an unprivileged user, own process group, firm timeout. ---
timeout -k 5 120 su -s /bin/bash runner -c "python3 /tests/collect_agent_output.py" > "$WORK_DIR/stage1.log" 2>&1
STAGE1_STATUS=$?
cat "$WORK_DIR/stage1.log"

# Sweep anything the candidate's code spawned/forked/detached under the
# runner UID before stage 2 (trusted) runs -- it cannot change its own UID.
pkill -9 -u runner 2>/dev/null

if [ $STAGE1_STATUS -ne 0 ] && [ $STAGE1_STATUS -ne 124 ]; then
  echo "Stage 1 exited abnormally (status $STAGE1_STATUS)"
fi
if [ ! -f "$WORK_DIR/trace.json" ]; then
  echo "Stage 1 failed to produce trace.json"
  write_reward "0"
  pkill -9 -u runner 2>/dev/null
  exit 0
fi

chmod 644 "$WORK_DIR/trace.json"

# --- Stage 2: trusted, root. Replays the recorded trace with no candidate
# code involved at all and independently recomputes the score. ---
cd /tests
timeout -k 5 60 python3 -m pytest test_dispatch_grading.py --ctrf="$CTRF_FILE" -v > "$WORK_DIR/stage2.log" 2>&1
STAGE2_STATUS=$?
cat "$WORK_DIR/stage2.log"

if [ $STAGE2_STATUS -eq 0 ]; then
  write_reward "1"
else
  write_reward "0"
fi

# Final sweep in case anything under the runner UID survived stage 2.
pkill -9 -u runner 2>/dev/null

exit 0
