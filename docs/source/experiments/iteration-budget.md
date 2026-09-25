# BB144 iteration-budget sweep

This flow measures logical word-failure probability against average executed
BP iterations at one physical error probability. Every point reuses one sample
corpus and one maximum-capacity Verilator artifact.

Vanilla BP:

```sh
DECODER=vanilla P_VALUE=0.003 \
MAX_BP_ITERATIONS="1 2 4 8 16 32 64 128 256 512 1024" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-vanilla-budget 10000
```

Relay-BP-S:

```sh
DECODER=relay RELAY_T0=60 RELAY_TR=60 RELAY_S=5 \
MAX_BP_ITERATIONS="60 120 180 300 540 1020 1980 3900 7740 15420 36060" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-relay-5-budget 10000
```

For Relay, each total budget must equal `T0 + R*Tr`. Outputs are:

- `results/budget_sweep.csv`
- `results/budget_sweep.json`
- `results/logical_failure_vs_average_iterations.png`
- `results/logical_failure_vs_average_iterations.pdf`

Ten thousand shots are a quick run, not a precise estimate of rates near
`1e-4`.
