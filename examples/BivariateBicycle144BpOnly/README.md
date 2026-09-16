# BB144 BP only

This is the runnable vanilla-BP benchmark for the pinned `[[144,12,12]]`
single-Z-check problem. Shared circuit preparation, Verilator transport, and
reporting live in [`benchmarks/bb144`](../../benchmarks/bb144/README.md), so
the BP-only and Relay-BP variants can use identical inputs without duplicating
benchmark code. `BpOnlyArtifact` contains the static BP datapath and output
controller, with no sorter or post-processor.

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

BP stops early when its correction satisfies the syndrome. At iteration 30 it
still streams the hard decision, but reports `bp_nonconverged`; the shared
analysis counts that shot as a decoder failure.

After the common dependencies are installed with `./scripts/setup-bb144.sh`,
run 1000 shots at each `p=0.001,0.002,...,0.007` on 16 cores:

```sh
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144BpOnly/run.sh \
  build/generated/bb144-bp-only 1000
```

This all-in-one command starts a fresh run: it removes the previous `source/`,
`artifact/`, `verification/`, `parallel/`, `raw/`, `results/`, and `.mill-out/` trees below
the selected output directory. For safety, automatic cleanup is accepted only
for a strict child of this repository's `build/generated/`. A run-local Mill
output tree avoids stale classes from another build; top-level notes and the
harmless `.matplotlib`/`.cache` directories are preserved. To resume an
interrupted shard run instead, invoke `benchmarks/rtl_shards/workflow.py`
directly on the existing `parallel/jobs.json`.

The default output is `build/generated/bb144-bp-only/`, split into `source/`,
`artifact/`, `verification/`, `parallel/`, `raw/`, and `results/`. Compare its
saved `source/benchmark.txt` with the future Relay-BP run to prove that both
decoders received identical inputs. The result tables are
`results/results.csv` and `results/timing.csv`; the primary combined plot is
`results/logical_failure_and_cycles.png`.
`results/logical_failure_rate_converged_only.png` separately reports logical
observable mismatches conditioned on BP convergence; nonconverged shots are
excluded from both its numerator and denominator.
