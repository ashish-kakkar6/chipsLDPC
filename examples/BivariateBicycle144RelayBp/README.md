# BB144 Relay-5, FPGA-paper Figure 7 parameter profile

This is the runnable Relay-BP benchmark for the pinned `[[144,12,12]]`
single-Z-check problem. It reuses the circuit preparation, Verilator transport,
CSV schema, and reporting in [`benchmarks/bb144`](../../benchmarks/bb144/README.md).
The generated `RelayBpArtifact` contains Relay-BP and the sparse correction
streamer, but no OSD hardware. Its final marginal and selected correction remain
available at the wrapper boundary for a future OSD or other post-processor.

The default configuration matches the stated parameters for the gross-code
Relay curve in Figure 7 of
[the FPGA paper](https://arxiv.org/abs/2510.21600v1): int4.2.8 arithmetic,
`gamma0=0.125`, requested `gamma` range `[-0.24,0.66]`, `beta_int=3,...,10`,
initial-leg limit `T0=80`, subsequent-leg limit `Tr=60`, and `R=600`
randomized relay legs after the initial leg. This follows Algorithm 1 and the
`trmue/relay` convention, so at most 601 total legs execute. The plot legend
identifies this curve as Relay-5, so the default
solution target is `S=5`. The initial `beta_int=7` gives
`gamma0=1-7/8=0.125`; subsequent legs draw one coefficient per variable from
`beta_int=3,...,10`, whose effective quantized gamma values range from `0.625`
to `-0.25`. Deterministic 16-bit Galois LFSRs generate the coefficients. The
coefficient source is chipsLDPC-specific. `artifact/config.json` records its
type, seed offset, coefficient range, and frame policy; the exact lane mapping
and recurrence are implemented in
[`LfsrRelayCoefficients`](../../src/main/scala/chipsldpc/RelayCoefficients.scala#L16).
Retain that source revision with the configuration. Every shot reseeds and
therefore uses the same reproducible coefficient schedule.

The paper's prose also describes `R` as a maximum total-leg count, while its
pseudocode runs leg zero followed by legs `1,...,R`. This example resolves that
off-by-one ambiguity in favor of the pseudocode and the golden repository. Use
`RELAY_R=599` if you instead want exactly 600 total legs.

As in the BP-only example, this benchmark measures the Z-check detector sector
of a circuit with **12 noisy extraction rounds and two noiseless closure
rounds**, implemented by
[`bb144.circuit`](../../benchmarks/bb144/bb144.py#L90) and
[`bb144.sample_physical`](../../benchmarks/bb144/bb144.py#L196).
The 72 raw detectors removed by exact singleton preprocessing leave 936
detectors; this reduction does not change the physical round count.
See the [model guide](../../docs/source/experiments/bb144-model.md).
This single-sector experiment does not reproduce a full XZ paper dataset.

Each leg stops when it finds a syndrome-consistent correction or reaches its
iteration limit. Relay stops after `S` solutions or after all configured legs.
Status is `bp_converged` (numeric 0) if any leg found a solution and
`bp_nonconverged` (numeric 2) otherwise. Among multiple solutions, the minimum
quantized-prior score wins and an equal score keeps the earlier solution. The
correction stream therefore carries the selected best solution, while
`softOutput` deliberately carries the final leg's marginals for downstream
post-processing. If no leg converges, the correction, residual, and marginal
are the coherent final-leg snapshot and status remains `bp_nonconverged`.
The relevant controller expressions are
[`candidateWins`, `legDone`, and `targetReached`](../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L112).
[`RelayBpExperimentProfile.decoderConfig`](../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L25)
maps the example's $R$ to the hardware's `maximumLegs = R + 1`; these experiment
defaults differ from the bare `RelayBpConfig` constructor defaults.

Relay iterations still take exactly two decoder clocks. Leg transitions reset
edge messages and advance coefficients on the existing commit clock, so they add no
control clocks. A nonblocking trace event marks the terminal VNU commit of every
leg. The Verilator harness timestamps consecutive events and records the exact
`index:iterations:cycles:converged` trace for each shot; it also checks that the
leg cycles sum to the reported BP cycles. These are deterministic decoder clocks,
not host simulation wall time. Convert them to time only using a synthesized
target's clock period; the paper's implementation reports 24 ns per BP iteration.
Its 12 ns decoder clock would make the configured full-leg caps 1.92 us for the
initial 160-clock leg and 1.44 us for each subsequent 120-clock leg.
These external-clock conversions are not measured chipsLDPC hardware timing.
[`checkRelayTiming`](../../benchmarks/bb144/sim_main.cpp#L283) checks the observed
trace against two clocks per executed iteration.

The sparse streamer emits asserted correction indices in
ascending order and the end-to-end always-ready latency is
`2 * total_iterations + 1 + occupied_banks + correction_weight`. The exact
Verilator result JSON records a structured `leg_timing` array. Its hardware leg
indices, and those in the compact sweep `leg_trace` field, are zero-based. The
report expands the trace with one-based leg numbers into
`results/relay_leg_timing.csv`, aggregates it by probability and leg number in
`results/relay_leg_timing_summary.csv`, and plots it in
`results/relay_leg_timing.png` alongside the BP-style logical-failure/cycle plots.

From the repository root, install the common dependencies with
[`./scripts/setup-bb144.sh`](../../scripts/setup-bb144.sh), then run 1,000 shots
at each `p=0.001,0.002,...,0.007` with 16 build/simulation workers:

```sh
P_VALUES="0.001 0.002 0.003 0.004 0.005 0.006 0.007" \
VERILATOR_JOBS=16 SIM_WORKERS=16 SHARD_SIZE=100 \
  ./examples/BivariateBicycle144RelayBp/run.sh \
  build/generated/bb144-relay-bp-new 1000
```

The Relay profile is independently configurable. This example fixes both the
shot count and probability instead of relying on defaults:

```sh
P_VALUES="0.003" RELAY_T0=80 RELAY_TR=60 RELAY_R=600 \
RELAY_S=5 RELAY_SEED_OFFSET=0 \
  ./examples/BivariateBicycle144RelayBp/run.sh \
  build/generated/bb144-relay-p003-new 1000
```

Without overrides, [`run.sh`](run.sh#L8) uses 10,000 shots per point and
`P_VALUES="0.001 0.002 0.003 0.004"`. Thus its defaults do not produce the
seven-point archived curve.

Every invocation is a fresh run. Cleanup is restricted to a strict child of
this repository's `build/generated/` and removes only generated source,
artifact, verification, shard, raw-result, report, and run-local Mill output
trees. Both Scala invocations use the same `MILL_OUTPUT_DIR` below the selected
output, eliminating stale results from the repository-wide Mill `out/` tree.

If `RELAY_REF_DIR` names the pinned, editable-installed `trmue/relay` checkout,
the run first checks the shared `beta_int` repetition fixture and archives its
provenance and result as `verification/trmue-relay.json`. The benchmark remains
self-contained when that optional environment variable is absent.

Before the sweep, the **first prepared shot at each probability** is checked
against an independent Scala golden computed by `Reference.runRelay` and
`Reference.lfsrBeta`, through
[`RelayBpSweepGolden.main`](../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L261)
and [`exactMain`](../../benchmarks/bb144/sim_main.cpp#L372). This is not an
all-shot full-vector software comparison. The default output is
`build/generated/bb144-relay-bp/`; its plots and summaries are under `results/`.
The external pinned `trmue/relay` adapter in `benchmarks/oracles/` is available
for additional cross-implementation fixtures.
