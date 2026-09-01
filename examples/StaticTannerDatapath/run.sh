#!/usr/bin/env bash
# Emit the exact Steane RTL, generate Scala LLR golden records, and compare them in Verilator.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

prior_sets=${1:-32}
iterations=${2:-4}
seed=${3:-0}
out=build/generated/static-tanner-artifact

./scripts/emit.sh static-steane "$out"
./mill chipsLDPC.test.runMain chipsldpc.StaticGolden \
  "$out/golden.txt" "$prior_sets" "$iterations" "$seed"
verilator --cc --exe --build -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
  -Wno-PINCONNECTEMPTY --top-module StaticTannerDatapath --Mdir "$out/obj_dir" \
  -CFLAGS -std=c++17 "$out/StaticTannerDatapath.sv" \
  examples/StaticTannerDatapath/sim_main.cpp
"$out/obj_dir/VStaticTannerDatapath" "$out/golden.txt"
