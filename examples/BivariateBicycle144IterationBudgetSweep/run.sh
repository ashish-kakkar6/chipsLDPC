#!/usr/bin/env bash
# Figure-4-style BB144 curve for one selectable BP-family decoder.
set -euo pipefail
shopt -s nullglob
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$root"

out=${1:-build/generated/bb144-iteration-budget-sweep}
shots=${2:-10000}
python=${PYTHON:-.venv/bin/python3}
decoder=${DECODER:-relay}
p=${P_VALUE:-0.003}
seed=${SEED:-14412}
jobs=${VERILATOR_JOBS:-16}
groups=${VERILATOR_GROUPS:-16}
workers=${SIM_WORKERS:-16}
shard_size=${SHARD_SIZE:-100}
t0=${RELAY_T0:-60}
tr=${RELAY_TR:-60}
solution_target=${RELAY_S:-5}
seed_offset=${RELAY_SEED_OFFSET:-0}

case "$decoder" in
  bp|vanilla) decoder=vanilla; defaults="1 2 4 8 16 32 64 128 256 512 1024" ;;
  relay) defaults="60 120 180 300 540 1020 1980 3900 7740 15420 36060" ;;
  *) echo "DECODER must be vanilla or relay: $decoder" >&2; exit 2 ;;
esac
read -r -a budgets <<< "${MAX_BP_ITERATIONS:-$defaults}"
((${#budgets[@]})) || { echo "MAX_BP_ITERATIONS is empty" >&2; exit 2; }
maximum=0
seen=" "
for budget in "${budgets[@]}"; do
  [[ $budget =~ ^[0-9]+$ && $budget -gt 0 ]] || {
    echo "invalid BP iteration budget: $budget" >&2; exit 2;
  }
  [[ $seen != *" $budget "* ]] || { echo "duplicate BP iteration budget: $budget" >&2; exit 2; }
  seen+="$budget "
  ((budget > maximum)) && maximum=$budget
done
if [[ $decoder == relay ]]; then
  for value in "$t0" "$tr" "$solution_target"; do
    [[ $value =~ ^[0-9]+$ && $value -gt 0 ]] || { echo "Relay limits must be positive" >&2; exit 2; }
  done
  [[ $seed_offset =~ ^[0-9]+$ && $seed_offset -lt 65535 ]] || {
    echo "RELAY_SEED_OFFSET must be in [0,65535)" >&2; exit 2;
  }
  for budget in "${budgets[@]}"; do
    ((budget >= t0 && (budget - t0) % tr == 0)) || {
      echo "Relay budget must equal T0 + R*Tr: $budget" >&2; exit 2;
    }
  done
  maximum_r=$(((maximum - t0) / tr))
fi

command -v "$python" >/dev/null || { echo "python not found: $python" >&2; exit 2; }
generated=$("$python" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' \
  "$root/build/generated")
out=$("$python" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$out")
case "$out" in "$generated"/*) ;; *) echo "output must be below $generated: $out" >&2; exit 2 ;; esac
[[ ! -e "$out" || -d "$out" ]] || { echo "output is not a directory: $out" >&2; exit 2; }
echo "Fresh run: clearing generated state in $out"
rm -rf -- "$out/source" "$out/artifact" "$out/verification" \
  "$out/parallel" "$out/raw" "$out/results" "$out/mill-out"
export MPLBACKEND=Agg MPLCONFIGDIR="$out/.matplotlib"
mkdir -p "$out/raw" "$out/results" "$out/verification"

problem_iterations=$([[ $decoder == vanilla ]] && echo "$maximum" || echo "$t0")
"$python" benchmarks/bb144/bb144.py prepare "$out/source" \
  --p "$p" --shots "$shots" --iterations "$problem_iterations" --seed "$seed"
problems=("$out"/source/verify/p*/problem.json)
((${#problems[@]} == 1)) || { echo "expected one prepared probability point" >&2; exit 2; }
problem=${problems[0]}
mill=(env MILL_OUTPUT_DIR="$out/mill-out" ./mill --no-server chipsLDPC.test.runMain)
if [[ $decoder == vanilla ]]; then
  "${mill[@]}" chipsldpc.BpOnlyExperiment "$problem" "$out"
  "${mill[@]}" chipsldpc.BpOnlySweepGolden \
    "$problem" "$out/verification/$(basename "$(dirname "$problem")")/golden.txt"
  top=BpOnlyArtifact
  define=BP_ONLY_ARTIFACT
  sim_name=VBpOnlyArtifact
  label="BB144 Z-check vanilla BP"
else
  profile=("$t0" "$tr" "$maximum_r" "$solution_target" "$seed_offset")
  "${mill[@]}" chipsldpc.RelayBpExperiment "$problem" "$out" "${profile[@]}"
  "${mill[@]}" chipsldpc.RelayBpSweepGolden "${profile[@]}" \
    "$problem" "$out/verification/$(basename "$(dirname "$problem")")/golden.txt"
  top=RelayBpArtifact
  define=RELAY_BP_ARTIFACT
  sim_name=VRelayBpArtifact
  label="BB144 Z-check Relay-$solution_target"
fi

sv=("$out"/artifact/rtl/*.sv)
((${#sv[@]})) || { echo "no emitted SystemVerilog" >&2; exit 2; }
obj="$out/verification/obj_dir"
ulimit -s "$(ulimit -Hs)"
MAKEFLAGS=-s verilator --cc --exe --build -j "$jobs" --output-groups "$groups" \
  -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-PINCONNECTEMPTY \
  --top-module "$top" --Mdir "$obj" -CFLAGS "-std=c++17 -D$define" \
  "${sv[@]}" benchmarks/bb144/sim_main.cpp
sim="$obj/$sim_name"
goldens=("$out"/verification/p*/golden.txt)
for golden in "${goldens[@]}"; do "$sim" "$golden" "$(dirname "$golden")/result.json"; done

"$python" benchmarks/rtl_shards/adapters/chipsldpc.py \
  "$out/source/benchmark.txt" "$sim" "$out/parallel" \
  --shard-size "$shard_size" --simulator-config "$out/artifact/config.txt" \
  --budgets "${budgets[@]}"
"$python" benchmarks/rtl_shards/workflow.py run "$out/parallel/jobs.json" \
  -j "$workers" --report "$out/parallel/run.json"
"$python" benchmarks/rtl_shards/workflow.py merge \
  "$out/parallel/jobs.json" "$out/raw/shots.csv"
"$python" benchmarks/bb144/budget_report.py \
  "$out/raw/shots.csv" "$out/source/sweep.json" "$out/parallel/run.json" \
  "$out/artifact/config.json" "$out/results" --label "$label"
