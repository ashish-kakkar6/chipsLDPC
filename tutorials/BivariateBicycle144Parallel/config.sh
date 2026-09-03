#!/usr/bin/env bash
# Shared, overrideable settings for every independent tutorial stage.
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"

OUT=${OUT:-build/tutorials/bb144-parallel}
PYTHON=${PYTHON:-.venv/bin/python3}
SHOTS_PER_P=${SHOTS_PER_P:-10000}
P_VALUES=${P_VALUES:-"0.001 0.002 0.003 0.004 0.005 0.006 0.007"}
MAX_P=${MAX_P:-0.007}
ITERATIONS=${ITERATIONS:-50}
SHARD_SIZE=${SHARD_SIZE:-500}
WORKERS=${WORKERS:-4}
CLOCK_CYCLES_PER_SHOT=${CLOCK_CYCLES_PER_SHOT:-$((2 + 2 * ITERATIONS))}

export MPLCONFIGDIR="$OUT/.matplotlib"
export MPLBACKEND=Agg
CACHE_DIR="$OUT/.cache"
