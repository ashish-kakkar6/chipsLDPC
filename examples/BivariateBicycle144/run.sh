#!/usr/bin/env bash
# Generate one Z-check BB144 artifact, then benchmark its 64/128/256 OSD ladder across p.
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
probabilities=${P_VALUES:-"0.001 0.002 0.003 0.004 0.005 0.006 0.007 0.008 0.009"}
read -r -a p_values <<< "$probabilities"
export MPLBACKEND=Agg MPLCONFIGDIR="$out/.matplotlib" XDG_CACHE_HOME="$out/.cache"
mkdir -p "$out/raw" "$out/results" "$out/verification"

"$python" examples/BivariateBicycle144/bb144.py prepare "$out/source" \
  --p "${p_values[@]}" --shots "$shots" --iterations 30
problems=("$out"/source/verify/p*/problem.json)
problem=${problems[0]}
[[ -f "$problem" ]] || { echo "no prepared problem" >&2; exit 2; }
./mill --no-server chipsLDPC.test.runMain chipsldpc.osd.BpFilteredOsd0Experiment \
  "$problem" "$out" "$k0" "$k1" "$k2"
golden_args=()
for problem in "${problems[@]}"; do
  tag=$(basename "$(dirname "$problem")")
  golden_args+=("$problem" "$out/verification/$tag/golden.txt")
done
./mill --no-server chipsLDPC.test.runMain chipsldpc.osd.BpFilteredOsd0SweepGolden \
  "$k0,$k1,$k2" "${golden_args[@]}"

sv=("$out"/artifact/rtl/*.sv)
obj="$out/verification/obj_dir-k${k0}-k${k1}-k${k2}"
ulimit -s "$(ulimit -Hs)"
MAKEFLAGS=-s verilator --cc --exe --build -j "$jobs" --output-groups "$groups" \
  -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
  --top-module BpFilteredOsd0Artifact --Mdir "$obj" -CFLAGS -std=c++17 \
  "${sv[@]}" examples/BivariateBicycle144/sim_main.cpp
sim="$obj/VBpFilteredOsd0Artifact"
for golden in "$out"/verification/p*/golden.txt; do
  "$sim" "$golden" "$(dirname "$golden")/result.json"
done
"$python" benchmarks/rtl_shards/adapters/chipsldpc.py \
  "$out/source/benchmark.txt" "$sim" "$out/parallel" \
  --shard-size "$shard_size" --simulator-config "$out/artifact/config.txt"
"$python" benchmarks/rtl_shards/workflow.py run "$out/parallel/jobs.json" \
  -j "$workers" --report "$out/parallel/run.json"
"$python" benchmarks/rtl_shards/workflow.py merge \
  "$out/parallel/jobs.json" "$out/raw/shots.csv"
"$python" examples/BivariateBicycle144/report.py \
  "$out/raw/shots.csv" "$out/source/sweep.json" "$out/parallel/run.json" "$out/results"
