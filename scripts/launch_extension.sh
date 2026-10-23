#!/usr/bin/env bash
# Launch the Luna extension runs DETACHED, so they survive this terminal/session ending.
# Resumable: rerun this script at any time; finished runs are skipped (scripts/extension_driver.py).
# Driver log: results/luna_extension/run.log · status: bash scripts/status.sh
#   bash scripts/launch_extension.sh              launch (refuses if a driver is already running)
#   bash scripts/launch_extension.sh --plan-only  checks + list of runs, no model calls
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/luna_extension
PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=.venv/bin/python
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

if [ "${1:-}" = "--plan-only" ]; then
  exec "$PY" scripts/extension_driver.py --plan-only
fi

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # Start-Process creates a process outside this shell's job, so it outlives the session.
    powershell.exe -NoProfile -Command "Start-Process -WindowStyle Hidden -FilePath '$(cygpath -w "$PWD/$PY")' \
      -ArgumentList 'scripts/extension_driver.py' -WorkingDirectory '$(cygpath -w "$PWD")' \
      -RedirectStandardOutput '$(cygpath -w "$PWD/results/luna_extension/driver.stdout.log")' \
      -RedirectStandardError '$(cygpath -w "$PWD/results/luna_extension/driver.stderr.log")'"
    ;;
  Darwin)
    nohup caffeinate -i "$PY" scripts/extension_driver.py >> results/luna_extension/driver.stdout.log 2>&1 < /dev/null &
    ;;
  *)
    setsid nohup "$PY" scripts/extension_driver.py >> results/luna_extension/driver.stdout.log 2>&1 < /dev/null &
    ;;
esac
echo "Launched detached. Log: results/luna_extension/run.log  Status: bash scripts/status.sh"
