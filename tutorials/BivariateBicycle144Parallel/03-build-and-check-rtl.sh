#!/usr/bin/env bash
# Compile one RTL artifact with Verilator and check every iteration at every p.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"
rtl=${RTL:-$OUT/artifact/rtl/StaticTannerArtifact.sv}
problems=("$OUT"/source/verify/p*/problem.json)
[[ -f "$rtl" && -f "${problems[0]}" ]] || { echo "missing RTL or prepared problems" >&2; exit 2; }

first=$(basename "$(dirname "${problems[0]}")")
if [[ -n ${SIM:-} ]]; then
  sim=$SIM
  "$sim" "$OUT/verification/$first/golden.txt" \
    "$OUT/verification/$first/result.json" compact
else
  VERILATOR_GROUPS=${VERILATOR_GROUPS:-16} ./examples/EndToEnd/verify.sh "$rtl" \
    "$OUT/verification/$first/golden.txt" "$OUT/verification/$first/result.json" compact
  sim="$OUT/verification/$first/obj_dir/VStaticTannerArtifact"
fi
for problem in "${problems[@]:1}"; do
  tag=$(basename "$(dirname "$problem")")
  "$sim" "$OUT/verification/$tag/golden.txt" \
    "$OUT/verification/$tag/result.json" compact
done
