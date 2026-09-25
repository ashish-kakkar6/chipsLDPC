# Systolic GF(2) solver

`src/main/scala/chipsldpc/GaussJordan/` contains a binary processing-element
mesh and a framed row-stream solver.

## Processing elements and mesh

`GjOpcode` fixes the two-bit row protocol:

| Value | Operation | Column behavior `(data output, next state)` |
| --- | --- | --- |
| `00` | `Pass` | `(input, state)` |
| `01` | `Swap` | `(state, input)` |
| `10` | `Add` | `(state XOR input, state)` |
| `11` | `Lock` | `(state, input)` |

`PeDiag` detects and stores pivots. `PeCol` applies the diagonal opcode to its
local bit. Both use active-high synchronous reset and hold registered state
when `en_i` is low.

`TrapezoidMeshConfig(n, liftedCols, reduceHopDelay, exposeFullState)` creates
`n` rows and `n + liftedCols` columns. Data moves down, opcodes move right, and
the reduce token moves between diagonal cells after `reduceHopDelay` enabled
clocks. Optional state exports are packed row-major. Emitted module names are
`pe_col`, `pe_diag`, and `trapeziod_mesh`.

## Framed solver

`SystolicGf2SolverConfig(width, maxRows)` fixes the coefficient width and row
capacity. One frame uses four Decoupled channels:

| Channel | Direction | Payload |
| --- | --- | --- |
| `start` | input | runtime row count and active coefficient columns |
| `row` | input | one `width`-bit coefficient row and one RHS bit |
| `solution` | output | logical slot, bit value, and `last` |
| `result` | output | consistency flag and solver clocks |

The solver handles one right-hand side per frame. It reverses active
coefficient columns at the mesh boundary because the physical mesh gives the
highest column first pivot priority. The public stream remains in ascending
logical-slot order. For a consistent rank-deficient system, dependent or free
slots are zero in the returned canonical witness.

The internal mesh uses `width` rows, one lifted RHS column, a reduce-hop delay
of three, and no full-state debug export. With a row accepted on every feed
clock, a nonempty frame reports

```{math}
\text{rows} + 3\,\text{width} + 1
```

solver clocks. A zero-row frame reports zero. Gaps while rows are supplied add
feed clocks. Solution and result backpressure do not change the captured solver
count.

Inconsistent frames emit no solution records. Consistent frames with nonzero
`activeCols` emit exactly that many records before the result.

## Inspect and test

```sh
./scripts/emit.sh pe-col
./scripts/emit.sh pe-diag
./scripts/emit.sh trapezoid-mesh
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.SystolicGf2SolverSpec
```

The full solver is also instantiated by [Filtered OSD-0](filtered-osd.md).
