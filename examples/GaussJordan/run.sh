#!/usr/bin/env bash
# Test both Gauss–Jordan PEs, emit their MLIR/SV, and lint each RTL artifact.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./scripts/emit.sh pe-col build/generated/gauss-jordan/pe-col
./scripts/emit.sh pe-diag build/generated/gauss-jordan/pe-diag
./scripts/verify-rtl.sh build/generated/gauss-jordan/pe-col/pe_col.sv pe_col
./scripts/verify-rtl.sh build/generated/gauss-jordan/pe-diag/pe_diag.sv pe_diag
