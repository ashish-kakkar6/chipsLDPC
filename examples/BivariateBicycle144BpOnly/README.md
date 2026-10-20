# BB144 BP only

This is the runnable vanilla-BP benchmark for the pinned `[[144,12,12]]`
single-Z-check problem. Shared circuit preparation, Verilator transport, and
reporting live in [`benchmarks/bb144`](../../benchmarks/bb144/README.md), so
the BP-only and Relay-BP variants can use identical inputs without duplicating
benchmark code. `BpOnlyArtifact` contains the static BP datapath and output
controller, with no sorter or post-processor.
See [`BpOnlyArtifact`](../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L8)
and the [circuit-model guide](../../docs/source/experiments/bb144-model.md).

The BP decision is passed through the reusable `SparseBitmaskStreamer`. The
stream contains only asserted correction indices, in ascending order; omitted
indices are zero. An empty correction emits no placeholder and is completed by
`resultValid`. The streamer snapshots 64-bit banks and spends one selection
clock per nonempty bank plus one transfer clock per asserted correction bit.
With an always-ready consumer, end-to-end clocks are therefore
`2 * completed_iterations + 1 + occupied_banks + correction_weight`.
The CSV's `bp_output_cycles` field covers both occupied-bank selection and
entry transfer. Artifact config ABI v2 records the bank width; regenerate the
RTL and simulator together rather than reusing a dense-output BP-only artifact.
[`SparseBitmaskStreamer`](../../src/main/scala/chipsldpc/SparseBitmaskStreamer.scala#L25)
implements the stream; [`checkSparseTiming`](../../benchmarks/bb144/sim_main.cpp#L305)
checks the clock equation with always-ready outputs. Input-file parsing and
external transport are outside that clock count.

BP stops when its correction satisfies the syndrome or it completes 30
iterations. If the last iteration is still inconsistent, it streams that hard
decision and reports `bp_nonconverged`; convergence on iteration 30 remains a
success. This branch is in
[`VanillaBpDecoder`](../../src/main/scala/chipsldpc/BpDecoder.scala#L84).
[`benchmarkMain`](../../benchmarks/bb144/sim_main.cpp#L528) counts failure for
nonconvergence or any logical-observable mismatch.

From the repository root, install the common dependencies with
[`./scripts/setup-bb144.sh`](../../scripts/setup-bb144.sh), then run 1,000 shots
at each `p=0.001,0.002,...,0.007` with 16 build/simulation workers:

```sh
P_VALUES="0.001 0.002 0.003 0.004 0.005 0.006 0.007" \
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144BpOnly/run.sh \
  build/generated/bb144-bp-only-new 1000
```

This all-in-one command starts a fresh run: it removes the previous `source/`,
`artifact/`, `verification/`, `parallel/`, `raw/`, `results/`, and `.mill-out/` trees below
the selected output directory. For safety, automatic cleanup is accepted only
for a strict child of this repository's `build/generated/`. A run-local Mill
output tree avoids stale classes from another build; top-level notes and the
harmless `.matplotlib`/`.cache` directories are preserved. To resume an
interrupted shard run instead, invoke `benchmarks/rtl_shards/workflow.py`
directly on the existing `parallel/jobs.json`.

Before the sweep,
[`BpOnlySweepGolden.main`](../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L163)
and [`exactMain`](../../benchmarks/bb144/sim_main.cpp#L372) compare the full result
of the first prepared shot at each probability against the Scala reference.
The bulk sweep does not independently compare every full correction/marginal
vector with that reference.

The default output is `build/generated/bb144-bp-only/`, split into `source/`,
`artifact/`, `verification/`, `parallel/`, `raw/`, and `results/`.
For a paired comparison, check the graph, logical map, and priors in
`source/sweep.json`, then the shot blocks in `source/benchmark.txt`. The first
benchmark header includes a decoder iteration cap, so entire vanilla/Relay
files can differ even when their physical inputs match. With the current
sampler, use the same shot count, probability order, seed, and numerical
environment, or reuse the saved corpus directly. The result tables are
`results/results.csv` and `results/timing.csv`; the primary combined plot is
`results/logical_failure_and_cycles.png`.
`results/logical_failure_rate_converged_only.png` separately reports logical
observable mismatches conditioned on BP convergence; nonconverged shots are
excluded from both its numerator and denominator.
