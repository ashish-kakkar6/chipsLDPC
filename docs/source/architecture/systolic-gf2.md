# Systolic GF(2) solver

[`TrapezoidMesh`](../../../src/main/scala/chipsldpc/GaussJordan/TrapezoidMesh.scala#L34)
connects binary processing elements; [`SystolicGf2Solver`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L38)
adds a framed row-stream interface.

## Processing elements and mesh

[`GjOpcode`](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L5)
fixes the two-bit row protocol. The table follows
[`PeCol`'s next-state logic](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L30):

| Value | Operation | Column behavior `(next registered data output, next state)` |
| --- | --- | --- |
| `00` | `Pass` | `(input, state)` |
| `01` | `Swap` | `(state, input)` |
| `10` | `Add` | `(state XOR input, state)` |
| `11` | `Lock` | `(state, input)` |

[`PeDiag`](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L48)
detects and stores pivots. [`PeCol`](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L12) applies the diagonal opcode to its
local bit. Both use active-high synchronous reset and hold registered state
when `en_i` is low. The table describes updates on an enabled clock edge;
reset takes priority. In contrast,
[`PeDiag.reduce_sig_o`](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L89)
is combinational (`reduce_sig_i && !rst`) and is not enable-gated.

The diagonal's [`next-state logic`](../../../src/main/scala/chipsldpc/GaussJordan/GaussJordanPE.scala#L68)
has a separate role: outside reduction, a zero emits `Pass`, the first one
sets the pivot state and emits `Lock`, and later ones emit `Add`. During
reduction it forwards the incoming data and emits `Swap` if a pivot is stored,
otherwise `Pass`.

[`TrapezoidMeshConfig(n, liftedCols, reduceHopDelay, exposeFullState)`](../../../src/main/scala/chipsldpc/GaussJordan/TrapezoidMesh.scala#L6) creates
`n` rows and `n + liftedCols` columns. Cells exist on and above the diagonal;
the lower-left triangle is tied to zero by
[`TrapezoidMesh`](../../../src/main/scala/chipsldpc/GaussJordan/TrapezoidMesh.scala#L47).
Data moves down, opcodes move right, and
the reduce token moves between diagonal cells after `reduceHopDelay` enabled
clocks. Optional state exports are packed row-major. Emitted module names are
`pe_col`, `pe_diag`, and `trapeziod_mesh`.

## Framed solver

[`SystolicGf2SolverConfig(width, maxRows)`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L6) fixes the coefficient width and row
capacity. One frame uses four Decoupled channels:

| Channel | Direction | Payload |
| --- | --- | --- |
| `start` | input | runtime row count and active coefficient columns |
| `row` | input | one `width`-bit coefficient row and one RHS bit |
| `solution` | output | logical slot, bit value, and `last` |
| `result` | output | consistency flag and solver clocks |

The [four payload bundles](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L16)
define the fields and widths; [`io`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L39)
defines the handshakes.

[`io.start.ready` and `io.row.ready`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L89)
accept one frame in idle, then rows only during the feed phase after one clear
clock. `rows` may be zero through `maxRows`, and `activeCols` may be zero through
`width`; the bounds are checked on
[`io.start.fire`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L99).
The solver consumes exactly `rows` handshakes. Only coefficient bits below
`activeCols` participate; higher bits are ignored.

The solver handles one right-hand side per frame. It reverses active
coefficient columns at the mesh boundary because the physical mesh gives the
highest column first pivot priority. The public stream remains in ascending
logical-slot order. For a consistent rank-deficient system, dependent or free
slots are zero in the returned canonical witness.
[`inputBits`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L67)
reverses columns; [`io.solution.bits`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L93)
restores logical slot order. The [`sRun` pivot mask](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L133)
sets slots without pivots to zero. "Canonical" refers to ascending logical
pivot priority with free variables set to zero, not a minimum-weight solution.

The internal mesh uses `width` rows, one lifted RHS column, a reduce-hop delay
of three, and no full-state debug export. With a row accepted on every feed
clock, a nonempty frame reports

```{math}
\text{rows} + 3\,\text{width} + 1
```

solver clocks. Here `width` is the elaborated mesh width, even if runtime
`activeCols` is smaller. A zero-row frame reports zero. If $G$ feed clocks have
no row handshake, the mathematical count becomes
$\text{rows}+G+3\,\text{width}+1$.
The equation counts the [`sFeed` and `sRun` increments](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L113):
one per feed clock, then `postCycle` from zero through `3 * width`
inclusive. It excludes the clear, output, and result phases.

[`SystolicGf2SolverConfig.cycleBits`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L13)
is $w_c=\max(1,\lceil\log_2(\text{maxRows}+3\,\text{width}+3)\rceil)$.
It covers unstalled frames; sufficiently long legal row gaps wrap `cycles`
modulo $2^{w_c}$. For example, `width = maxRows = 1` uses three counter bits:
one row plus three empty feed clocks takes eight counted clocks and reports
zero. The row-gap interface remains usable, but this counter is not an
unbounded latency measurement. Solution and result backpressure do not change
the captured solver count.

Inconsistent frames emit no solution records. Consistent frames with nonzero
`activeCols` emit exactly that many records, including zero-valued bits, before
the result. Zero rows yield an all-zero witness; zero active columns yield no
solution records and are consistent only if every supplied RHS is zero.
[`sOutput`](../../../src/main/scala/chipsldpc/GaussJordan/SystolicGf2Solver.scala#L141)
holds the current slot and value until accepted, and `sResult` holds the result
until accepted. A new frame cannot start before that result handshake.

## Inspect and test

```sh
./scripts/emit.sh pe-col
./scripts/emit.sh pe-diag
./scripts/emit.sh trapezoid-mesh
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.SystolicGf2SolverSpec
```

[`GaussJordanPESpec`](../../../src/test/scala/chipsldpc/GaussJordan/GaussJordanPESpec.scala#L34)
enumerates all column and diagonal transitions and checks reset/enable behavior.
[`TrapezoidMeshSpec`](../../../src/test/scala/chipsldpc/GaussJordan/TrapezoidMeshSpec.scala#L181)
compares registered paths with a cycle oracle, including enable stalls and
reduce-hop delays.
[`SystolicGf2SolverSpec`](../../../src/test/scala/chipsldpc/GaussJordan/SystolicGf2SolverSpec.scala#L62)
checks full-rank, rank-deficient, inconsistent, and empty systems; exhausts
two-column systems through three rows; and samples taller three-column systems.
Those solver tests use contiguous rows and unstalled outputs; the row-gap and
backpressure behavior above follows the production state machine.

The full solver is also instantiated by [Filtered OSD-0](filtered-osd.md).
