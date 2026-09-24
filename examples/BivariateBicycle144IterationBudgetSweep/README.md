# BB144 iteration-budget sweep

This meta-example produces a
[Figure-4-style](https://arxiv.org/pdf/2510.21600v1) curve for one selected
integer decoder: logical word-failure probability versus average executed BP
iterations at one physical error probability. Every point uses the same
deterministic BB144 Z-check shots and one maximum-capacity Verilator artifact;
the stopping budget is a runtime input.

Select vanilla BP:

```sh
DECODER=vanilla P_VALUE=0.003 \
MAX_BP_ITERATIONS="1 2 4 8 16 32 64 128 256 512 1024" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-vanilla-budget 10000
```

Or select one Relay-BP-S profile:

```sh
DECODER=relay RELAY_T0=60 RELAY_TR=60 RELAY_S=5 \
MAX_BP_ITERATIONS="60 120 180 300 540 1020 1980 3900 7740 15420 36060" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-relay-5-budget 10000
```

For Relay, every total budget must be `T0 + R*Tr`; the implementation converts
it to the repository convention of `R` randomized legs after the initial leg.
The plotted failure probability is the raw shot-level event: nonconvergence or
any mismatch among the 12 logical observables. It is not divided among logical
operators or converted to a per-QEC-cycle rate.

The outputs are `results/logical_failure_vs_average_iterations.{png,pdf}` and
`results/budget_sweep.{csv,json}`. Resolving a rate near `1e-4` normally needs
substantially more than the 10,000-shot quick run. `VERILATOR_JOBS`,
`VERILATOR_GROUPS`, and `SIM_WORKERS` all default to 16; lower `SIM_WORKERS`
first if the machine is memory-constrained.
