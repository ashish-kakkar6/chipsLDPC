#!/usr/bin/env bash
# Reduce raw records into logical-rate, lifetime, timing tables, and plots only.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
mkdir -p "$MPLCONFIGDIR" "$CACHE_DIR"
XDG_CACHE_HOME="$CACHE_DIR" "$PYTHON" tutorials/BivariateBicycle144Parallel/analyze.py \
  "$OUT/raw/shots.csv" "$OUT/source/sweep.json" "$OUT/parallel/jobs.json" \
  "$OUT/parallel/run.json" "$OUT/results"
