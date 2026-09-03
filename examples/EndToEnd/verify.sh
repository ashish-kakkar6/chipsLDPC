#!/usr/bin/env bash
# Compile one emitted artifact and compare every iteration with Scala golden records.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project_root"

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 <artifact.sv> <golden.txt> <result.json> [full|compact]" >&2
  exit 2
fi
sv=$1
golden=$2
result=$3
mode=${4:-full}
obj_dir=$(dirname "$golden")/obj_dir
jobs=${VERILATOR_JOBS:-4}
groups=${VERILATOR_GROUPS:-$jobs}
mkdir -p "$(dirname "$result")"

MAKEFLAGS=-s verilator --cc --exe --build -j "$jobs" --output-groups "$groups" \
  -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
  -Wno-PINCONNECTEMPTY --top-module StaticTannerArtifact --Mdir "$obj_dir" \
  -CFLAGS -std=c++17 "$sv" examples/EndToEnd/sim_main.cpp
"$obj_dir/VStaticTannerArtifact" "$golden" "$result" "$mode"
