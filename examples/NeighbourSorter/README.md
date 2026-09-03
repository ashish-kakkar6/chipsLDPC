# Neighbour sorter example

This is the [Section 3.1 two-phase sorter](https://doi.org/10.1140/epjqt/s40507-025-00446-y)
configured for eight signed, seven-bit soft outputs from `StaticTannerDatapath` and the static rule
`abs(soft) < 4`.

Run its Verilator-backed behavior and cycle tests, then emit inspectable
FIRRTL-dialect MLIR and SystemVerilog:

```sh
./examples/NeighbourSorter/run.sh
```

The default-scope test deliberately drives every `inScope` bit low while
`inScopeValid` is low. The mask is therefore ignored and all threshold-eligible
indices are considered. With BP soft values

```text
[-16, 2, -1, -4, 0, -3, 8, -2]
```

the emitted `(soft, index)` stream is:

```text
(0, 4), (-1, 2), (2, 1), (-2, 7), (-3, 5)
```

Values with magnitude four or greater are excluded. Setting `inScopeValid`
intersects the static threshold with the runtime `inScope` mask; it never
widens the threshold.

The input and output are standard Decoupled interfaces. `out.last` marks the
last eligible value and `done` also covers an empty result. A producer must hold
the input frame until `in.fire`; when adapting the current BP `Valid` result,
either schedule it only while `in.ready` is high or add a one-entry holding
register.

Starting with the input-acceptance clock, the sorter scans N indices and drains
K eligible values in exactly N + K active cycles when `out.ready` stays high.
The test also checks the paper's full-set case, K = N, takes exactly 2N cycles,
that backpressure adds only stalled cycles, and that an empty scope terminates
after N cycles.

Generated files are under:

```text
build/generated/neighbour-sorter/NeighbourSorter.fir.mlir
build/generated/neighbour-sorter/NeighbourSorter.sv
```
