# Filtered OSD-0

The post-processor has three components:

- [`NeighbourSorter`](../../../src/main/scala/chipsldpc/sort/NeighbourSorter.scala)
  filters and orders soft values;
- [`FilteredOsd0`](../../../src/main/scala/chipsldpc/osd/FilteredOsd0.scala)
  constructs reduced systems and controls progressive attempts; and
- [`BpFilteredOsd0`](../../../src/main/scala/chipsldpc/osd/BpFilteredOsd0.scala)
  connects fixed-budget BP to the OSD fallback.

## Filtering and order

`NeighbourSorter` accepts one parallel soft frame and an optional runtime scope.
Eligibility uses a strict threshold:

- `SignedAscending`: include `soft < threshold`, then order by signed value;
- `MagnitudeAscending`: include `abs(soft) < threshold`, then order by
  magnitude.

Equal values retain ascending variable index. For $N$ inputs and $K$ eligible
outputs, an unstalled run takes $N+K$ active clocks; sorting all inputs takes
$2N$.

## Progressive solve

`FilteredOsd0Config.prefixes` is a strictly increasing list of selected-column
capacities. The sorter runs once. The controller keeps at most the largest
prefix, constructs each selected parity-check column from the elaborated graph,
and streams active rows to the matching [GF(2) solver](systolic-gf2.md).

An active row has either a selected coefficient or an asserted syndrome bit.
If a prefix is inconsistent and more selected columns exist, the controller
tries the next prefix without sorting again. It does not perform a separate
linear-independence pass; rank deficiency is handled by the solver. When
`rejectOverflow` is true, more eligible values than the largest prefix produce
`Overflow` without a solve.

The correction stream contains `(index, value, last)` records in selected-slot
order. The result reports `Solved`, `Inconsistent`, or `Overflow`, plus selected
columns, active rows, total controller clocks, and accumulated solver clocks.
Correction or result backpressure can extend interface latency.

## BP composition

`BpFilteredOsd0` runs up to its configured BP iteration count and checks
convergence after each complete two-clock iteration. A converged BP result is
streamed directly. Otherwise, the final marginals, stored syndrome, and
optional scope launch `FilteredOsd0` without a host round trip.

Its result distinguishes `BpConverged`, `OsdSolved`, `OsdInconsistent`, and
`OsdOverflow`, and separates BP, OSD, and solver cycle counts. The maintained
BB144 BP artifacts do not instantiate this post-processor.

## Inspect and test

```sh
./scripts/emit.sh bp-filtered-osd0-steane
./mill chipsLDPC.test.testOnly chipsldpc.sort.NeighbourSorterSpec
./mill chipsLDPC.test.testOnly chipsldpc.osd.FilteredOsd0Spec
./mill chipsLDPC.test.testOnly chipsldpc.osd.BpFilteredOsd0Spec
```

