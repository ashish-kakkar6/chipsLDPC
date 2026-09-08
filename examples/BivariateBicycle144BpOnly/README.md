# BB144 BP-only comparison

This experiment is paired with
[`BivariateBicycle144`](../BivariateBicycle144/README.md): it reuses the same
pinned single-Z-check circuit generator, deterministic shots, quantization,
30-iteration BP limit, Verilator harness, sharding workflow, CSV schema, and
plotting script. Only the emitted decoder changes. `BpOnlyArtifact` contains
the static BP datapath and output controller, with no sorter or OSD solver.

BP stops early when its correction satisfies the syndrome. At iteration 30 it
still streams the hard decision, but reports `bp_nonconverged`; the shared
analysis counts that shot as a decoder failure.

After the common dependencies are installed with `./scripts/setup-bb144.sh`,
run 1000 shots at each `p=0.001,0.002,...,0.009` on 16 cores:

```sh
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144BpOnly/run.sh \
  build/generated/bb144-bp-only 1000
```

The default output is `build/generated/bb144-bp-only/`; its `source/`,
`artifact/`, `verification/`, `parallel/`, `raw/`, and `results/` layout is
identical to the BP+OSD run. The exact same sampled input can be confirmed with:

```sh
cmp build/generated/bb144-bp-only/source/benchmark.txt \
  build/generated/bb144-progressive-osd0/source/benchmark.txt
```

Compare `results/results.csv`, `results/timing.csv`, and
`results/logical_failure_and_cycles.png` between the two output directories.
