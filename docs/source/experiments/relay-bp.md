# BB144 Relay-BP

This flow runs the Relay-5 profile on the same deterministic BB144 Z-check
problem as BP-only. It contains Relay-BP and the sparse correction streamer,
without OSD hardware.
[`RelayBpArtifact`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L32)
wraps [`RelayBpDecoder`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L50)
and the sparse correction streamer for this experiment.

[Circuit model and matrix sizes](bb144-model.md) ·
[Archived Relay results and data](bb144-results.md) ·
[Relay equations and leg diagram](../architecture/relay-bp.md)

The default profile uses `T0=80`, `Tr=60`, `R=600`, and `S=5`. Here `R` is the
number of randomized legs after leg zero, so at most 601 legs execute.
[`RelayBpExperimentProfile.decoderConfig`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L25)
performs the `relayLegs + 1` conversion. These are experiment-profile defaults;
the `RelayBpConfig` constructor's own defaults differ.

From the repository root, run 1,000 shots at each of seven explicit probabilities:

```sh
P_VALUES="0.001 0.002 0.003 0.004 0.005 0.006 0.007" \
RELAY_T0=80 RELAY_TR=60 RELAY_R=600 RELAY_S=5 RELAY_SEED_OFFSET=0 \
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144RelayBp/run.sh \
  build/generated/bb144-relay-bp-new 1000
```

The [run script's defaults](../../../examples/BivariateBicycle144RelayBp/run.sh#L8)
are 10,000 shots per point and only $p=.001,.002,.003,.004$ if the arguments
and `P_VALUES` above are omitted. The script
[clears the selected output directory](../../../examples/BivariateBicycle144RelayBp/run.sh#L45)
before emission; keep archived runs in separate directories.

The maximum work is

```{math}
B=T_0+RT_r=80+600\times60=36{,}080
```

iterations, calculated by
[`RelayBpConfig.maximumIterations`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L25).
[`RelayBpDecoder.legDone` and `targetReached`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L115)
allow early stopping; success means at least one converged leg, even when the
target of five solutions is not reached. Its
[`candidateScore` and `candidateWins`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L111)
select the minimum immutable-prior score, keeping the first candidate on ties.
The selected correction and final-leg marginal can describe different legs.

[`RelayBpSweepGolden.main`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L261)
generates the first-shot fixtures checked by
[`exactMain`](../../../benchmarks/bb144/sim_main.cpp#L372). During the sweep,
[`checkRelayTiming`](../../../benchmarks/bb144/sim_main.cpp#L283) checks leg traces
and their totals; this is distinct from independently checking every output
vector against a software decoder.

[`report.main`](../../../benchmarks/bb144/report.py#L350) writes `results.csv`,
`results.json`, and the failure/clock plots under `results/`.
[`report.write_relay_leg_outputs`](../../../benchmarks/bb144/report.py#L273)
writes `relay_leg_timing.csv`, `relay_leg_timing_summary.csv`, and
`relay_leg_timing.png`. It converts hardware leg index zero to displayed leg
number one. [`checkSparseTiming`](../../../benchmarks/bb144/sim_main.cpp#L305)
checks the total clock formula, including correction streaming.

Failure classification is in
[`benchmarkMain`](../../../benchmarks/bb144/sim_main.cpp#L528): unsuccessful
decoder status or any logical-observable mismatch. The benchmark covers one
Z-check sector; it is not a full XZ reproduction of a paper dataset.
