# BB144 Relay-BP

This flow runs the Relay-5 profile on the same deterministic BB144 Z-check
problem as BP-only. It contains Relay-BP and the sparse correction streamer,
without OSD hardware.

The default profile uses `T0=80`, `Tr=60`, `R=600`, and `S=5`. Here `R` is the
number of randomized legs after leg zero, so at most 601 legs execute.

Run 1,000 shots for each configured physical error probability:

```sh
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144RelayBp/run.sh \
  build/generated/bb144-relay-bp 1000
```

Override the Relay limits explicitly when needed:

```sh
RELAY_T0=80 RELAY_TR=60 RELAY_R=600 RELAY_S=5 \
  ./examples/BivariateBicycle144RelayBp/run.sh
```

Reports are written below `results/`, including the logical-failure summary
and per-leg timing tables. The benchmark covers one Z-check sector; it is not a
full XZ reproduction of a paper dataset.
