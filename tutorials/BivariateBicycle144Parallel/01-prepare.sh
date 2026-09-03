#!/usr/bin/env bash
# Construct the BB144 matrices/DEM and deterministically sample benchmark inputs.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
mkdir -p "$MPLCONFIGDIR" "$CACHE_DIR"
read -r -a p_values <<< "$P_VALUES"
"$PYTHON" tutorials/BivariateBicycle144Parallel/prepare.py "$OUT/source" \
  --p "${p_values[@]}" --shots "$SHOTS_PER_P" --iterations "$ITERATIONS"
