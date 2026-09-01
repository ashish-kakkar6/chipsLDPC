#!/usr/bin/env bash
# Run every Scala reference and Verilator-backed Chisel behavioral test.
set -euo pipefail
exec ./mill chipsLDPC.test
