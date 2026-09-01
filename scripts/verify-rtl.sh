#!/usr/bin/env bash
# Lint emitted SV without Chisel; allow CIRCT's intentional open output pins.
set -euo pipefail
rtl=${1:-build/generated/iteration/MinSumIteration2x2.sv}
top=${2:-MinSumIteration2x2}
exec verilator --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
  -Wno-PINCONNECTEMPTY --top-module "$top" "$rtl"
