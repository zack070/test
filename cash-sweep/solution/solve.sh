#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p /app/outputs
cp "$SCRIPT_DIR/policy.py" /app/outputs/policy.py
