#!/usr/bin/env bash
# Verify BP-soft ordering and exact latency in Verilator, then emit and lint the same toy configuration.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

out=build/generated/neighbour-sorter
./mill chipsLDPC.test.testOnly chipsldpc.sort.NeighbourSorterSpec
./scripts/emit.sh neighbour-sorter "$out"
./scripts/verify-rtl.sh "$out/NeighbourSorter.sv" NeighbourSorter
