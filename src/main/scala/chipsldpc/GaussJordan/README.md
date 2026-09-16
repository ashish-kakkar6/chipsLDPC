# Systolic Gauss–Jordan hardware

This folder contains the independent one-bit processing elements used by a
binary systolic Gauss–Jordan mesh.

`GjOpcode` fixes the two-bit mesh protocol:

| Value | Operation | Column behavior `(data_o, next state)` |
| --- | --- | --- |
| `00` | `Pass` | `(data_i, state)` |
| `01` | `Swap` | `(state, data_i)` |
| `10` | `Add` | `(state ^ data_i, state)` |
| `11` | `Lock` | `(state, data_i)` |

During reduction, `data_i` is forwarded; a locked diagonal emits `Swap` and an
unlocked diagonal emits `Pass`. Outside reduction, zero passes, the first one
locks the state, and later ones emit `Add`.

Both modules use active-high synchronous reset and hold their registers when
`en_i` is low. `PeDiag.reduce_sig_o` is deliberately combinational and is not
enable-gated. The generated modules retain the legacy `pe_col` and `pe_diag`
port ABI (from systolicLDPC). Chisel lowers `GjOpcode` ports to two-bit nets; a mixed handwritten-SV
mesh may therefore keep its existing `gj_pkg.sv`, while an all-Chisel mesh does
not need that package. In a mixed build, replace rather than also compile the
handwritten `pe_col.sv` and `pe_diag.sv` to avoid duplicate module definitions.

`TrapezoidMesh` composes these cells into `n` rows and `n + liftedCols`
columns. The inactive lower-left triangle is tied off, while data moves down,
opcodes move right, and reduction moves between diagonal cells after
`reduceHopDelay` enabled cycles. State exports use row-major packed order.
`TrapezoidMeshConfig` is validated Scala elaboration data and introduces no
runtime configuration hardware. Each configuration emits a
MLIR/SystemVerilog artifact.

`SystolicGf2Solver` adds framed row and indexed-solution streams without
changing the mesh. Its boundary reverses active columns because the physical
mesh gives its highest column first pivot priority. The public stream therefore
uses ascending logical pivots and returns the canonical witness with every
dependent/free column zero. It consumes the direct diagonal-state output and
suppresses the mesh's debug-only full-state exports, avoiding quadratic debug
wires in production RTL. Tests compare the exact vector with an independent
GF(2) model; every two-column system through three rows is checked exhaustively.

Run `GaussJordanPESpec`, `TrapezoidMeshSpec`, and `SystolicGf2SolverSpec` for
focused checks. Use `scripts/emit.sh pe-col`, `scripts/emit.sh pe-diag`, or
`scripts/emit.sh trapezoid-mesh` when an inspectable MLIR/SystemVerilog
artifact is needed; separate example wrappers would duplicate those tests.
