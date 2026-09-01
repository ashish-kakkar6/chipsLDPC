# Systolic Gauss–Jordan hardware

This folder contains the independent one-bit processing elements used by a
binary systolic Gauss–Jordan mesh. They intentionally depend on no BP message
or configuration type, so a future controller can schedule them as a separate
post-processing stage.

`GjOpcode` fixes the two-bit mesh protocol:

| Value | Operation | Column behavior `(data_o, next state)` |
| --- | --- | --- |
| `00` | `Pass` | `(data_i, state)` |
| `01` | `Swap` | `(state, data_i)` |
| `10` | `Add` | `(state ^ data_i, state)` |
| `11` | `Lock` | `(state, data_i)` |

`PeDiag` gives reduction highest priority. A set state and asserted
`reduce_sig_i` emit `Swap` and forward `data_i`; otherwise a zero passes, the
first one locks the state, and later ones emit `Add`.

Both modules use active-high synchronous reset and hold their registers when
`en_i` is low. `PeDiag.reduce_sig_o` is deliberately combinational and is not
enable-gated. The generated modules retain the legacy `pe_col` and `pe_diag`
port ABI. Chisel lowers `GjOpcode` ports to two-bit nets; a mixed handwritten-SV
mesh may therefore keep its existing `gj_pkg.sv`, while an all-Chisel mesh does
not need that package. In a mixed build, replace rather than also compile the
handwritten `pe_col.sv` and `pe_diag.sv` to avoid duplicate module definitions.

`TrapezoidMesh` composes these cells into `n` rows and `n + liftedCols`
columns. The inactive lower-left triangle is tied off, while data moves down,
opcodes move right, and reduction moves between diagonal cells after
`reduceHopDelay` enabled cycles. State exports use row-major packed order.
`TrapezoidMeshConfig` is validated Scala elaboration data and introduces no
runtime configuration hardware. It deliberately omits the streamed row count
`M`, which belongs to a future feeder. Each configuration emits one specialized
MLIR/SystemVerilog artifact rather than a parameterized SystemVerilog module.

See the runnable [PE](../../../../../examples/GaussJordan/README.md) and
[mesh](../../../../../examples/GaussJordan/TrapezoidMesh/README.md) examples
for focused tests and inspectable MLIR/SystemVerilog emission.
