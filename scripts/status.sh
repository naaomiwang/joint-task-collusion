#!/usr/bin/env bash
# Runs completed / remaining and spend for the Luna extension, no outcomes.
# Also writes results/luna_extension/RUN_STATE.md.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=.venv/bin/python
PYTHONUTF8=1 "$PY" scripts/status.py
