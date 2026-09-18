#!/usr/bin/env bash
# Verifier entry point. Runs as root. Never uses set -e: every path,
# including a crash, must still reach the point where reward.txt gets
# written. No candidate code runs in this container at all -- the
# artifact is a data file, so this is just: read it, diff it against the
# sealed ground truth, write the reward.

REWARD_DIR=/logs/verifier
REWARD_FILE="$REWARD_DIR/reward.txt"
CTRF_FILE="$REWARD_DIR/ctrf.json"

mkdir -p "$REWARD_DIR"
chown root:root "$REWARD_DIR"
chmod 700 "$REWARD_DIR"

chown -R root:root /tests/sealed
chmod 700 /tests/sealed
find /tests/sealed -type f -exec chmod 600 {} \;
find /tests/sealed -type d -exec chmod 700 {} \;

write_reward() {
  echo -n "$1" > "$REWARD_FILE"
  chown root:root "$REWARD_FILE"
  chmod 600 "$REWARD_FILE"
}

cd /tests
timeout -k 5 60 python3 -m pytest test_withholding_grading.py --ctrf="$CTRF_FILE" -v > /tmp/stage.log 2>&1
STATUS=$?
cat /tmp/stage.log

if [ $STATUS -eq 0 ]; then
  write_reward "1"
else
  write_reward "0"
fi

exit 0
