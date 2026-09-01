#!/usr/bin/env bash
# Test the toy mesh, emit its MLIR/SV, and lint the emitted RTL artifact.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$project_root"

out=build/generated/gauss-jordan/trapezoid-mesh
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./scripts/emit.sh trapezoid-mesh "$out"
./scripts/verify-rtl.sh "$out/trapeziod_mesh.sv" trapeziod_mesh
