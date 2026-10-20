# BB144 iteration-budget sweep

This meta-example produces a
[Figure-4-style](https://arxiv.org/pdf/2510.21600v1) curve for one selected
integer decoder: logical word-failure probability versus average executed BP
iterations at one physical error probability. Every point uses the same
deterministic BB144 Z-check shots and one maximum-capacity Verilator artifact;
the stopping budget is a runtime input.
[`chipsldpc.plan`](../../benchmarks/rtl_shards/adapters/chipsldpc.py#L73) reuses
each shard input for all selected budgets. This matches the type of plot in
the cited study, not its full-code dataset or hardware timing.

Run commands from the repository root after
[`./scripts/setup-bb144.sh`](../../scripts/setup-bb144.sh). Select vanilla BP:

```sh
DECODER=vanilla P_VALUE=0.003 \
MAX_BP_ITERATIONS="1 2 4 8 16 32 64 128 256 512 1024" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-vanilla-budget-new 10000
```

Or select one Relay-BP-S profile:

```sh
DECODER=relay P_VALUE=0.003 RELAY_T0=60 RELAY_TR=60 RELAY_S=5 \
MAX_BP_ITERATIONS="60 120 180 300 540 1020 1980 3900 7740 15420 36060" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-relay-5-budget-new 10000
```

For Relay, every total budget must be `T0 + R*Tr`; the implementation converts
it to the repository convention of `R` randomized legs after the initial leg.
[`decoderRuntimeLimit`](../../benchmarks/bb144/sim_main.cpp#L265) checks
divisibility and capacity, then supplies `R + 1` to the runtime leg-limit port.
Vanilla uses the requested budget directly as its iteration limit.
The plotted failure probability is the raw shot-level event: nonconvergence or
any mismatch among the 12 logical observables. It is not divided among logical
operators or converted to a per-QEC-cycle rate.
It is classified by
[`benchmarkMain`](../../benchmarks/bb144/sim_main.cpp#L528).
[`budget_report.summarize`](../../benchmarks/bb144/budget_report.py#L14)
computes the mean executed iterations, Wilson 95% failure interval, and
`1.96 * sample_stdev(iterations) / sqrt(shots)` halfwidth for the mean. These
are executed-work statistics, not configured caps or measured nanoseconds.

The outputs are `results/logical_failure_vs_average_iterations.{png,pdf}` and
`results/budget_sweep.{csv,json}`. At a true failure probability of `1e-4`,
10,000 shots give only one expected failure. `VERILATOR_JOBS`,
`VERILATOR_GROUPS`, and `SIM_WORKERS` all default to 16; lower `SIM_WORKERS`
first if the machine is memory-constrained.

[`run.sh`](run.sh#L61) clears the selected generated output before each run.
Keep earlier experiments in separate directories. It checks the first prepared
shot against the maximum-capacity Scala golden before sweeping runtime caps;
it does not independently compare all shots at all caps with a software
decoder. The current reporter checks coverage and iteration bounds, then
aggregates the harness's saved failure flags.

The [archived documentation curve](../../docs/source/experiments/bb144-results.md)
uses a different list, `60 120 180 300 540 1020 2040 4080`, with 20,000 shots.
Changing the shot count or probability order changes the current sampler's
corpus; retain saved inputs when making paired comparisons.
