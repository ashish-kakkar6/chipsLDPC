#!/usr/bin/env bash
# Generate one Z-check BB144 artifact, verify it exactly, then benchmark its 64/128/256 OSD ladder.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"

out=${1:-build/generated/bb144-progressive-osd0}
shots=${2:-1000}
k0=${3:-64}
k1=${4:-128}
k2=${5:-256}
python=${PYTHON:-.venv/bin/python3}
jobs=${VERILATOR_JOBS:-4}
groups=${VERILATOR_GROUPS:-16}
workers=${SIM_WORKERS:-4}
shard_size=${SHARD_SIZE:-100}
mkdir -p "$out/raw" "$out/results" "$out/verification"

"$python" examples/BivariateBicycle144/bb144.py prepare "$out/source" \
  --p 0.005 --shots "$shots" --iterations 30
problem="$out/source/verify/p0_0050/problem.json"
./mill --no-server chipsLDPC.test.runMain chipsldpc.osd.BpFilteredOsd0Experiment \
  "$problem" "$out" "$k0" "$k1" "$k2"

sv=("$out"/artifact/rtl/*.sv)
obj="$out/verification/obj_dir-k${k0}-k${k1}-k${k2}"
ulimit -s "$(ulimit -Hs)"
MAKEFLAGS=-s verilator --cc --exe --build -j "$jobs" --output-groups "$groups" \
  -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
  --top-module BpFilteredOsd0Artifact --Mdir "$obj" -CFLAGS -std=c++17 \
  "${sv[@]}" examples/BivariateBicycle144/sim_main.cpp
sim="$obj/VBpFilteredOsd0Artifact"
"$sim" "$out/verification/golden.txt" "$out/verification/result.json"
"$python" benchmarks/rtl_shards/adapters/chipsldpc.py \
  "$out/source/benchmark.txt" "$sim" "$out/parallel" \
  --shard-size "$shard_size" --simulator-config "$out/artifact/config.txt"
"$python" benchmarks/rtl_shards/workflow.py run "$out/parallel/jobs.json" \
  -j "$workers" --report "$out/parallel/run.json"
"$python" benchmarks/rtl_shards/workflow.py merge \
  "$out/parallel/jobs.json" "$out/raw/shots.csv"
"$python" examples/BivariateBicycle144/report.py "$out/raw/shots.csv" "$out/results"
