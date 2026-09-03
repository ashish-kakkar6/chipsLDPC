#!/usr/bin/env bash
# Run immutable stimulus shards as independent simulator processes and merge CSV.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
sim=${SIM:-$OUT/verification/p0_0010/obj_dir/VStaticTannerArtifact}
[[ -x "$sim" ]] || { echo "missing simulator: $sim" >&2; exit 2; }

python3 benchmarks/rtl_shards/adapters/chipsldpc.py "$OUT/source/benchmark.txt" \
  "$sim" "$OUT/parallel" --shard-size "$SHARD_SIZE" \
  --max-p "$MAX_P" --clock-cycles-per-shot "$CLOCK_CYCLES_PER_SHOT"
python3 benchmarks/rtl_shards/workflow.py run "$OUT/parallel/jobs.json" \
  -j "$WORKERS" --report "$OUT/parallel/run.json"
python3 benchmarks/rtl_shards/workflow.py check "$OUT/parallel/jobs.json"
python3 benchmarks/rtl_shards/workflow.py merge "$OUT/parallel/jobs.json" "$OUT/raw/shots.csv"
