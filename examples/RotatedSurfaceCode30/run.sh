#!/usr/bin/env bash
# Build and exactly simulate fixed 30-iteration d=3,5,7 rotated-surface decoders.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

out_root=${1:-build/generated/rotated-surface-30}
python=${PYTHON:-.venv/bin/python3}
for distance in 3 5 7; do
  out="$out_root/d$distance"
  "$python" examples/RotatedSurfaceCode/surface_code.py generate \
    "$distance" "$out" --iterations 30
  ./mill --no-server chipsLDPC.test.runMain chipsldpc.EmitSystemVerilogExperiment \
    "$out/stim/problem.json" "$out"
  ./examples/EndToEnd/verify.sh "$out/rtl/StaticTannerArtifact.sv" \
    "$out/verification/golden.txt" "$out/result.json" compact
  "$python" examples/RotatedSurfaceCode/surface_code.py report "$out"
done
