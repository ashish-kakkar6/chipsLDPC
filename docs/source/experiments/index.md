# Experiments

```{toctree}
:maxdepth: 1
:hidden:

BB144 circuit model <bb144-model>
Archived BB144 results <bb144-results>
BP only <bp-only>
Relay BP <relay-bp>
Iteration budget <iteration-budget>
```

The experiment flows use the pinned `[[144,12,12]]` BB144 Z-check problem.
BP-only and Relay-BP share circuit preparation, deterministic shots, Verilator
transport, and reporting.

| Experiment stage | Implementation entry point |
| --- | --- |
| Circuit, DEM, priors, and physical samples | [`bb144.prepare`](../../../benchmarks/bb144/bb144.py#L273), calling `circuit`, `z_check_model`, `sample_physical`, and `quantize` |
| Vanilla artifact and first-shot reference | [`BpOnlyExperiment.main`](../../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L132), [`BpOnlySweepGolden.main`](../../../src/test/scala/chipsldpc/BpOnlyExperiment.scala#L163) |
| Relay artifact and first-shot reference | [`RelayBpExperiment.main`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L242), [`RelayBpSweepGolden.main`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L261) |
| RTL shot execution and logical classification | [`decode`](../../../benchmarks/bb144/sim_main.cpp#L129), [`benchmarkMain`](../../../benchmarks/bb144/sim_main.cpp#L458) |
| Shared input shards and result merge | [`chipsldpc.plan`](../../../benchmarks/rtl_shards/adapters/chipsldpc.py#L26), [`workflow.merge`](../../../benchmarks/rtl_shards/workflow.py#L153) |
| Probability and work summaries | [`report.summarize`](../../../benchmarks/bb144/report.py#L99), [`budget_report.summarize`](../../../benchmarks/bb144/budget_report.py#L14) |

Start with the [circuit and detector model](bb144-model.md), then inspect the
[three archived result plots](bb144-results.md). Each plot has its original
settings, data downloads, and an offline regeneration path. The guides below
run new experiments in explicitly selected output directories.

Install their Python dependencies once:

```sh
./scripts/setup-bb144.sh
```

[`setup-bb144.sh`](../../../scripts/setup-bb144.sh#L1) installs the numerical
dependencies used by these scripts. Run commands from the repository root;
the individual guides link the exact run script and its accepted settings.

Generated RTL, raw samples, and reports are written below `build/generated/`.
Keep the saved configuration, source description, Git revision, and tool
versions with any published result.

The current generator writes schema `chipsldpc.bb144.v2` in
[`bb144.prepare`](../../../benchmarks/bb144/bb144.py#L307). The probability
report writes `chipsldpc.bb144-decoder-sweep.v1` in
[`report.main`](../../../benchmarks/bb144/report.py#L402); the budget report
writes `chipsldpc.bb144-iteration-budget-sweep.v1` in
[`budget_report.main`](../../../benchmarks/bb144/budget_report.py#L106).
The run scripts check a prepared first-shot fixture for each probability;
they do not currently perform independent full-vector checks for every shot.
