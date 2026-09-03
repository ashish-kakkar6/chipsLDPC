#!/usr/bin/env bash
# Unit-check each block, then verify the exact emitted hierarchy against the software golden model.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

out=build/generated/bp-filtered-osd0-steane
./mill chipsLDPC.test.testOnly \
  chipsldpc.sort.NeighbourSorterSpec \
  chipsldpc.GaussJordan.SystolicGf2SolverSpec \
  chipsldpc.osd.FilteredOsd0Spec \
  chipsldpc.osd.BpFilteredOsd0Spec
./scripts/emit.sh bp-filtered-osd0-steane "$out"
./mill chipsLDPC.test.runMain chipsldpc.osd.BpFilteredOsd0Golden "$out/golden.txt"
verilator --cc --exe --build -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
  -Wno-PINCONNECTEMPTY \
  --top-module BpFilteredOsd0 --Mdir "$out/obj_dir" -CFLAGS -std=c++17 \
  "$out/BpFilteredOsd0.sv" examples/BpFilteredOsd0/sim_main.cpp
"$out/obj_dir/VBpFilteredOsd0" "$out/golden.txt"
