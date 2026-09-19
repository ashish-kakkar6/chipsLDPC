#!/usr/bin/env bash
# Emit Relay-BP BB144 RTL, verify it exactly, then run the shared parallel sweep.
set -euo pipefail
shopt -s nullglob
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"

out=${1:-build/generated/bb144-relay-bp}
shots=${2:-10000}
python=${PYTHON:-.venv/bin/python3}
jobs=${VERILATOR_JOBS:-16}
groups=${VERILATOR_GROUPS:-16}
workers=${SIM_WORKERS:-16}
shard_size=${SHARD_SIZE:-100}
initial_iterations=${RELAY_T0:-80}
relay_iterations=${RELAY_TR:-60}
relay_legs=${RELAY_R:-600}
solution_target=${RELAY_S:-5}
seed_offset=${RELAY_SEED_OFFSET:-0}
probabilities=${P_VALUES:-"0.0005 0.001 0.002 0.003 0.004 0.005"}
read -r -a p_values <<< "$probabilities"

positive() {
  [[ $2 =~ ^[0-9]+$ && $2 -ge $3 ]] || {
    echo "$1 must be an integer >= $3: $2" >&2
    exit 2
  }
}
positive RELAY_T0 "$initial_iterations" 1
positive RELAY_TR "$relay_iterations" 1
positive RELAY_R "$relay_legs" 0
positive RELAY_S "$solution_target" 1
positive RELAY_SEED_OFFSET "$seed_offset" 0
((seed_offset < 65535)) || { echo "RELAY_SEED_OFFSET must be < 65535" >&2; exit 2; }

command -v "$python" >/dev/null || { echo "python not found: $python" >&2; exit 2; }
generated=$("$python" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' \
  "$root/build/generated")
out=$("$python" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$out")
case "$out" in
  "$generated"/*) ;;
  *) echo "refusing to clean output outside $generated: $out" >&2; exit 2 ;;
esac
[[ ! -e "$out" || -d "$out" ]] || { echo "output is not a directory: $out" >&2; exit 2; }
mill_output="$out/mill-out"
echo "Fresh run: clearing generated state in $out"
rm -rf -- "$out/source" "$out/artifact" "$out/verification" \
  "$out/parallel" "$out/raw" "$out/results" "$mill_output"

export MPLBACKEND=Agg MPLCONFIGDIR="$out/.matplotlib"
mkdir -p "$out/raw" "$out/results" "$out/verification"

if [[ -n ${RELAY_REF_DIR:-} ]]; then
  "$python" benchmarks/oracles/trmue_relay.py \
    benchmarks/oracles/fixtures/repetition_beta_int.json --pretty \
    > "$out/verification/trmue-relay.json"
fi

"$python" benchmarks/bb144/bb144.py prepare "$out/source" \
  --p "${p_values[@]}" --shots "$shots" --iterations "$initial_iterations"
problems=("$out"/source/verify/p*/problem.json)
((${#problems[@]})) || { echo "no prepared problems" >&2; exit 2; }
problem=${problems[0]}
profile=("$initial_iterations" "$relay_iterations" "$relay_legs" \
  "$solution_target" "$seed_offset")
MILL_OUTPUT_DIR="$mill_output" ./mill --no-server chipsLDPC.test.runMain \
  chipsldpc.RelayBpExperiment "$problem" "$out" "${profile[@]}"
golden_args=()
for problem in "${problems[@]}"; do
  tag=$(basename "$(dirname "$problem")")
  golden_args+=("$problem" "$out/verification/$tag/golden.txt")
done
MILL_OUTPUT_DIR="$mill_output" ./mill --no-server chipsLDPC.test.runMain \
  chipsldpc.RelayBpSweepGolden "${profile[@]}" "${golden_args[@]}"

sv=("$out"/artifact/rtl/*.sv)
((${#sv[@]})) || { echo "no emitted SystemVerilog" >&2; exit 2; }
obj="$out/verification/obj_dir"
ulimit -s "$(ulimit -Hs)"
MAKEFLAGS=-s verilator --cc --exe --build -j "$jobs" --output-groups "$groups" \
  -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
  --top-module RelayBpArtifact --Mdir "$obj" \
  -CFLAGS "-std=c++17 -DRELAY_BP_ARTIFACT" \
  "${sv[@]}" benchmarks/bb144/sim_main.cpp
sim="$obj/VRelayBpArtifact"
goldens=("$out"/verification/p*/golden.txt)
((${#goldens[@]})) || { echo "no verification goldens" >&2; exit 2; }
for golden in "${goldens[@]}"; do
  "$sim" "$golden" "$(dirname "$golden")/result.json"
done
"$python" benchmarks/rtl_shards/adapters/chipsldpc.py \
  "$out/source/benchmark.txt" "$sim" "$out/parallel" \
  --shard-size "$shard_size" --simulator-config "$out/artifact/config.txt"
"$python" benchmarks/rtl_shards/workflow.py run "$out/parallel/jobs.json" \
  -j "$workers" --report "$out/parallel/run.json"
"$python" benchmarks/rtl_shards/workflow.py merge \
  "$out/parallel/jobs.json" "$out/raw/shots.csv"
label="BB144 Z-check Relay-$solution_target"
if ((initial_iterations == 80 && relay_iterations == 60 && \
      relay_legs == 600 && solution_target == 5)); then
  label+=" (FPGA paper Fig. 7 parameter profile)"
fi
"$python" benchmarks/bb144/report.py \
  "$out/raw/shots.csv" "$out/source/sweep.json" "$out/parallel/run.json" "$out/results" \
  --label "$label" \
  --decoder-config "$out/artifact/config.json"
