# Filtered OSD-0

The post-processor has three components:

- [`NeighbourSorter`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L48)
  filters and orders soft values;
- [`FilteredOsd0`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L59)
  constructs reduced systems and controls progressive attempts; and
- [`BpFilteredOsd0`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L51)
  connects BP with a finite iteration budget to the OSD fallback.

## Filtering and order

[`NeighbourSorter.included`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L69)
applies a strict threshold to one parallel soft frame; the input scope can
further exclude variables:

- `SignedAscending`: include `soft < threshold`, then order by signed value;
- `MagnitudeAscending`: include `abs(soft) < threshold`, then order by
  magnitude.

The scope mask is applied only when `inScopeValid` is true.
[`FilteredOsd0Config.order`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L19)
defaults to signed order; the standalone
[`NeighbourSorterConfig.order`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L14)
defaults to magnitude order.

[`NeighbourSorter.precedes`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L74)
breaks ties by ascending variable index. For $N$ inputs and $K$ eligible
outputs, an unstalled run takes $N+K$ clocks **including the input-acceptance
edge**: the input handshake inserts the first value, $N-1$ fill clocks scan the
rest, and $K$ handshakes drain the result. Sorting all inputs takes $2N$.
[`NeighbourSorter.io.in.fire`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L94)
and its [`sFill` branch](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L125)
implement the scan. The
[`io.out.fire` branch](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala#L167)
advances the drain; output backpressure holds the current entry and adds clocks.
`done` pulses after the last output, or after the scan when $K=0$.

## Progressive solve

[`FilteredOsd0Config.prefixes`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L21)
is a strictly increasing list of selected-column
capacities. The sorter runs once. The controller keeps at most the largest
prefix, constructs each selected parity-check column from the elaborated graph,
and streams active rows to the matching [GF(2) solver](systolic-gf2.md).
[`FilteredOsd0.solvers`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L96)
instantiates a separate fixed-width solver for each configured prefix. For
prefix capacity $p$, `solveCount` is the smaller of $p$ and the retained-column
count; that value becomes the solver's runtime `activeCols`.

For the ordered selected-column list $S=(j_0,\ldots,j_{k-1})$, form $H_S$
in that same slot order and solve

```{math}
H_S x=\boldsymbol\sigma,\qquad
\hat e_S=x,\quad \hat e_{\overline S}=0.
```

[`solver.io.row`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L116)
receives the selected coefficients and original syndrome. The returned bits
form an absolute correction; the controller does not XOR them into BP's hard
decision.

[`FilteredOsd0.rowsByAttempt`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L88)
marks a row active when it has a selected coefficient or an asserted syndrome bit.
Thus an all-zero coefficient row with RHS one is retained as a contradiction;
only rows of the form $0=0$ are omitted. Rows are streamed in ascending original
row order by [`nextRow`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L93).
If a prefix is inconsistent and more selected columns exist, the controller
tries the next prefix without sorting again. It does not perform a separate
linear-independence pass; rank deficiency is handled by the solver. When
`rejectOverflow` is true, more eligible values than the largest prefix produce
`Overflow` without a solve.
The [`canRetry` and `retry` signals](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L133)
select another prefix; the [`sSort` completion branch](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L184)
handles overflow.

With `rejectOverflow = false`, excess eligible columns are discarded after the
largest prefix is retained. With no selected columns, a zero syndrome yields
`Solved` with an empty correction stream; a nonzero syndrome yields
`Inconsistent`. `Solved` asserts linear consistency, not logical correctness.

The correction stream contains `(index, value, last)` records in selected-slot
order, including slots whose value is zero. This is the sorter's soft-value
order, not generally ascending original variable index. Inconsistent and
overflow results emit no correction records.
The result reports `Solved`, `Inconsistent`, or `Overflow`, plus the current
attempt's selected count, active rows, controller clocks, and accumulated solver
clocks. `selected` is `solveCount`, not the total number of eligible variables;
on overflow, it and `activeRows` describe the first planned prefix.
Correction or result backpressure can extend interface latency.
[`io.correction` and `io.result`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L139)
map solver slots back to original variable indices and expose those statuses
and counters. The [`cycles` update](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala#L164)
stops once the result is valid, so a stalled result handshake extends interface
latency without extending that counter.

The controller accepts a new frame only after the previous result handshake.
Its 32-bit `cycles` includes sorting, setup, retries, and correction stalls.
`solverCycles` sums the completed attempts' solver counters and the current
attempt's counter, excluding their output stalls. Overflow reports zero solver
clocks. These finite-width counters are not saturating elapsed-time clocks.

## BP composition

`BpFilteredOsd0` runs up to its configured BP iteration count and checks
convergence after each complete two-clock iteration. A converged BP result is
streamed directly as all $N$ `(index, value)` entries, including zeros, in
ascending variable-index order. Otherwise, the final marginals, stored syndrome, and
optional scope launch `FilteredOsd0` without a host round trip.
[`BpFilteredOsd0.stopBp` and `launchOsd`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L72)
define that handoff and wire the BP marginals into the post-processor.
[`io.correction`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L93)
selects the full BP stream or the selected-slot OSD stream. The scope mask
restricts OSD candidates; it does not restrict the BP iteration.

Its result distinguishes `BpConverged`, `OsdSolved`, `OsdInconsistent`, and
`OsdOverflow`, and separates BP, OSD, and solver cycle counts. The maintained
BB144 BP artifacts do not instantiate this post-processor.
See [`DecodeStatus`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L9)
and the [`io.result` assignments](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L103).

For $I$ completed BP iterations, `bpCycles` is $2I$. With unstalled correction
output, the top-level `cycles` value is $2I+1+N$ on BP convergence and
$2I+1+\text{osdCycles}$ on fallback. The extra clock consumes the registered BP
result and performs the branch handoff; it is not another BP iteration.
[`BpFilteredOsd0.cycles`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala#L125)
counts from the accepted frame until the result becomes valid, excluding final
result backpressure. Correction stalls extend this count, but not `bpCycles`.

## Inspect and test

```sh
./scripts/emit.sh bp-filtered-osd0-steane
./mill chipsLDPC.test.testOnly chipsldpc.sort.NeighbourSorterSpec
./mill chipsLDPC.test.testOnly chipsldpc.osd.FilteredOsd0Spec
./mill chipsLDPC.test.testOnly chipsldpc.osd.BpFilteredOsd0Spec
```

[`NeighbourSorterSpec`](../../../src/test/scala/chipsldpc/sort/NeighbourSorterSpec.scala#L89)
checks threshold boundaries, scope, ordering, empty output, odd/single input
sizes, and output stalls.
[`FilteredOsd0Spec`](../../../src/test/scala/chipsldpc/osd/FilteredOsd0Spec.scala#L120)
checks selected corrections, overflow, progressive attempts, cycle counts, and
result stalls. [`BpFilteredOsd0Spec`](../../../src/test/scala/chipsldpc/osd/BpFilteredOsd0Spec.scala#L76)
checks early BP exit and OSD handoff against the independent reference.
