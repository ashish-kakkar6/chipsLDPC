# BP-filtered-OSD0

This Steane example composes the static min-sum datapath, signed-LLR neighbour
sorter, and systolic GF(2) mesh. It runs at most 30 complete BP iterations,
exits when `H * HD == syndrome`, and otherwise solves on indices with signed
soft value `< 1` (`0.5` at the repository's scale of two). A runtime scope is
optional; `inScopeValid = 0` means all indices.

Run the block tests and the exact emitted-SystemVerilog regression:

```sh
./examples/BpFilteredOsd0/run.sh
```

The script writes inspectable MLIR and the complete module hierarchy to
`build/generated/bp-filtered-osd0-steane/`. Its C++ driver compiles that exact
`.sv` file with Verilator and checks status, indexed corrections, and every
cycle counter against an independent Scala BP/GF(2) model.

`correction` is an indexed stream. BP convergence emits all `n` hard-decision
bits; OSD emits the `K` selected assignments and implies zero elsewhere. The
terminal status distinguishes BP convergence, OSD success, inconsistency, and
filter overflow.

Column lookup and `H_R` assembly happen while sorted indices drain, so they add
no separate extraction pass. The row-stream mesh starts once `H_R` is complete;
the sorter/inverter overlap in Figure 8 of [Báscones et al.](https://link.springer.com/article/10.1140/epjqt/s40507-025-00446-y)
belongs to its column-oriented standard-OSD architecture, not the rank-deficient
filtered solver used here.

With no stalls, BP reports exactly `2I` datapath clocks for `I` complete
iterations. The sorter takes `N + K` clocks. Each fixed-width solver reports
`m' + 3R + 1`; configured fallbacks report the sum for every attempted
prefix. [Maurya et al.](https://arxiv.org/html/2511.21660v2)'s fixed-width mesh baseline is
`m' + 3Rmax - 1`; dynamically stopping at `K` would target `m' + 3K - 1` but
needs additional control. Thus the current wrapper exposes a two-clock framing
gap against the appropriate fixed-width baseline. The `2N + 3M` result in
the standard-OSD paper describes a different inversion flow and is not the
latency target for this filtered rank-deficient solver.

`prefixes` are strictly increasing elaboration-time hardware widths. See the
[BB144 example](../BivariateBicycle144/README.md) for the main unfiltered
all-column configuration with prefixes 64, 128, and 256.
