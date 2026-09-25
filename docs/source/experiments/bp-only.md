# BB144 BP-only

This flow runs the autonomous vanilla-BP decoder on deterministic BB144
Z-check shots. A shot fails when BP does not converge or its correction has a
logical-observable mismatch.

Run 1,000 shots for each configured physical error probability:

```sh
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144BpOnly/run.sh \
  build/generated/bb144-bp-only 1000
```

The command starts a fresh run in the selected output directory. Results are
written to:

- `results/results.csv`
- `results/timing.csv`
- `results/logical_failure_and_cycles.png`

The artifact emits asserted correction indices in ascending order. A
nonconverged final iteration still emits its hard decision and is counted as a
decoder failure.
