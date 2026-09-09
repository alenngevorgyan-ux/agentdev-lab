#!/usr/bin/env bash
# AgentDev Lab -- one-command setup and verification.
#
# There is nothing to install: the lab is standard-library only. This script
# verifies the environment, runs every authoritative suite, and leaves you with
# a working dashboard.
#
#   ./setup.sh              verify only
#   ./setup.sh --sample     also seed clearly-labelled synthetic data
#   ./setup.sh --dashboard  seed sample data and open the dashboard

set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
SEED_SAMPLE=0
RUN_DASHBOARD=0

for arg in "$@"; do
  case "$arg" in
    --sample)    SEED_SAMPLE=1 ;;
    --dashboard) SEED_SAMPLE=1; RUN_DASHBOARD=1 ;;
    -h|--help)   sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

step "Checking Python"
$PY - <<'PYCHECK'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11+ is required; found {sys.version.split()[0]}")
print(f"Python {sys.version.split()[0]} at {sys.executable}")
print("dependencies: none (standard library only)")
PYCHECK

step "Task registry"
$PY -m benchmark list

step "Unit and integration suite"
$PY -m unittest discover -s tests -t . -q

step "Harness self-check (controls validate every task)"
$PY -m benchmark selfcheck

step "Integrity audit"
$PY -m benchmark verify-integrity || echo "(findings above are disclosed, not hidden)"

if [ "$SEED_SAMPLE" -eq 1 ]; then
  step "Seeding synthetic development data"
  $PY -m benchmark seed-sample
fi

step "Ready"
cat <<'NEXT'
Common commands:

  python3 -m benchmark list                          registered tasks
  python3 -m benchmark run --adapter oracle          upper control (expect 100%)
  python3 -m benchmark run --adapter noop            lower control (expect 0%)
  python3 -m benchmark sql                           list the 24 SQL analyses
  python3 -m benchmark sql 03 --scope sample         run one against sample data
  python3 -m benchmark dashboard --scope sample      local dashboard on :8765
  python3 -m benchmark export --format csv --out out CSV export

Measuring a real agent needs credentials in the environment, for example:

  ANTHROPIC_API_KEY=... python3 -m benchmark run --adapter claude-code \
      --agent claude-code --model claude-opus-5 --attempts 5
NEXT

if [ "$RUN_DASHBOARD" -eq 1 ]; then
  step "Starting the dashboard"
  exec $PY -m benchmark dashboard --scope sample
fi
