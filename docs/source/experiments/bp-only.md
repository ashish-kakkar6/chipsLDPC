# BB144 BP-only

This flow runs the autonomous vanilla-BP decoder on deterministic BB144
Z-check shots. A shot fails when BP does not converge or its correction has a
logical-observable mismatch.
[`BpOnlyArtifact`](../../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L8)
connects [`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L41)
to the correction streamer. The harness's
[`benchmarkMain`](../../../benchmarks/bb144/sim_main.cpp#L528) computes the
logical-observable mask and the `logical_failure` flag.

[Circuit model and matrix sizes](bb144-model.md) ·
[Archived vanilla results and data](bb144-results.md)

From the repository root, run 1,000 shots at each of seven probabilities:

```sh
P_VALUES="0.001 0.002 0.003 0.004 0.005 0.006 0.007" \
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144BpOnly/run.sh \
  build/generated/bb144-bp-only-new 1000
```

The [BP-only run script](../../../examples/BivariateBicycle144BpOnly/run.sh#L34)
prepares a 30-iteration problem, emits RTL with
[`BpOnlyExperiment.main`](../../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L132),
and checks the first prepared shot at each probability using
[`BpOnlySweepGolden.main`](../../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L163)
and [`exactMain`](../../../benchmarks/bb144/sim_main.cpp#L372).
The remaining sweep runs through `benchmarkMain`; the script does not perform
an independent full-vector software comparison for every shot.

The command [clears the selected generated output](../../../examples/BivariateBicycle144BpOnly/run.sh#L26)
before running. Choose a new directory to retain earlier results.
[`report.main`](../../../benchmarks/bb144/report.py#L350) writes:

- `results/results.csv`
- `results/results.json`
- `results/timing.csv`
- `results/logical_failure_and_cycles.png`

[`SparseBitmaskStreamer`](../../../src/main/scala/chipsldpc/SparseBitmaskStreamer.scala#L25)
emits asserted correction indices in ascending order.
[`VanillaBpDecoder`'s terminal branch](../../../src/main/scala/chipsldpc/BpDecoder.scala#L84)
returns its final decision even when the iteration cap is reached without
convergence; the harness still counts that shot as a failure.

The current profile uses four message-magnitude bits plus a sign and seven
signed marginal bits, from
[`RelayDefaults.q`](../../../src/main/scala/chipsldpc/Config.scala#L8).
With always-ready outputs, the wrapper's measured clock count is

```{math}
C=2I+1+N_{\mathrm{occupied\ banks}}+w(\hat e),
```

where $I$ is the number of completed iterations and $w(\hat e)$ is correction
weight. [`checkSparseTiming`](../../../benchmarks/bb144/sim_main.cpp#L305)
checks this equation for each shot. It excludes input-file parsing and external
transport time; converting clocks to seconds requires a measured target clock.
