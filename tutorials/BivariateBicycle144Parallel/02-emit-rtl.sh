#!/usr/bin/env bash
# Elaborate the static Tanner graph once and write RTL plus Scala golden trajectories.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
problems=("$OUT"/source/verify/p*/problem.json)
[[ -f "${problems[0]}" ]] || { echo "run 01-prepare.sh first" >&2; exit 2; }

./mill --no-server chipsLDPC.test.runMain chipsldpc.EmitSystemVerilogExperiment \
  "${problems[0]}" "$OUT/artifact"
golden_args=()
for problem in "${problems[@]}"; do
  tag=$(basename "$(dirname "$problem")")
  mkdir -p "$OUT/verification/$tag"
  golden_args+=("$problem" "$OUT/verification/$tag/golden.txt")
done
./mill --no-server chipsLDPC.test.runMain chipsldpc.WriteGolden "${golden_args[@]}"
