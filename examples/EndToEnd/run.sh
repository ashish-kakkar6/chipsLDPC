#!/usr/bin/env bash
# Read one problem, emit specialized RTL/golden records, and compare the exact RTL in Verilator.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

problem=${1:-examples/EndToEnd/problem.json}
out=${2:-build/generated/end-to-end}

./mill --no-server chipsLDPC.test.runMain chipsldpc.EndToEnd "$problem" "$out"
./examples/EndToEnd/verify.sh \
  "$out/StaticTannerArtifact.sv" "$out/golden.txt" "$out/result.json"
