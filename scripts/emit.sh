#!/usr/bin/env bash
# Emit FIRRTL-dialect MLIR and SystemVerilog for one named example top.
set -euo pipefail
top=${1:-iteration}
out=${2:-build/generated/$top}
exec ./mill chipsLDPC.runMain chipsldpc.Generate "$top" "$out"
