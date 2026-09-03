#!/usr/bin/env bash
# Generate one Stim rotated-surface problem, verify its exact RTL, and record its logical outcome.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

distance=${1:-3}
out=${2:-build/generated/rotated-surface-d$distance}
iterations=${3:-8}
python=${PYTHON:-.venv/bin/python3}

"$python" examples/RotatedSurfaceCode/surface_code.py \
  generate "$distance" "$out" --iterations "$iterations"
./examples/EndToEnd/run.sh "$out/stim/problem.json" "$out/rtl"
"$python" examples/RotatedSurfaceCode/surface_code.py check "$out"
