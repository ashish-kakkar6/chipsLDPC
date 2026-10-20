# BB144 benchmark support

This directory is shared infrastructure, not a third decoder example. It keeps
the physical experiment fixed while
[`examples/BivariateBicycle144BpOnly`](../../examples/BivariateBicycle144BpOnly/README.md)
and
[`examples/BivariateBicycle144RelayBp`](../../examples/BivariateBicycle144RelayBp/README.md)
select different BP implementations.

- [`bb144.prepare`](bb144.py#L273) constructs the pinned Z-check circuit,
  detector error model, integer priors, physical circuit samples, logical rows,
  and first-shot verification fixtures.
- [`decode`](sim_main.cpp#L129) drives a generated Verilator artifact.
  [`benchmarkMain`](sim_main.cpp#L458) writes one raw CSV row per shot and
  computes failure from decoder status and the correction's logical action.
- [`report.main`](report.py#L350) checks shot coverage, clock totals, and Relay
  trace consistency, then writes timing and failure summaries.
  [`report.summarize`](report.py#L99) sums the harness's `logical_failure`
  flags; it does not independently rederive or validate those flags.
- [`budget_report.summarize`](budget_report.py#L14) reports word-failure
  probability against mean executed iterations without a per-cycle transform.
- [`requirements.txt`](requirements.txt) pins the Python-side dependencies.

The physical circuit has 12 noisy rounds and two noiseless closure rounds.
[`sample_physical`](bb144.py#L157) samples faults at circuit locations; it does
not draw independent DEM-column errors. The graph is the Z-check detector
sector, with exact singleton preprocessing to 936 checks, 8,784 fault-signature
variables, and 30,672 edges. See the
[model and metric definitions](../../docs/source/experiments/bb144-model.md).

[`per_qec_cycle`](report.py#L59) computes the equivalent rate
`1 - (1 - P_word) ** (1 / 12)`; it is a normalization of whole-shot failure,
not a direct per-round or per-logical-qubit count. Its input includes
nonconvergence. The separately reported converged-only rate excludes those
shots and has a different denominator.

[`prepare`](bb144.py#L307) writes schema `chipsldpc.bb144.v2`, including Stim's
version and the root seed. The current sampler uses `seed + probability_index`
and sequential NumPy array draws; changing shot count or probability order
changes the corpus. `z_checks.stim` is only the first probability's circuit;
each probability has its own DEM. Keep the saved benchmark, probability list,
source revision, numerical environment, artifact configuration, and raw CSVs
for reproducibility. Matching a seed or a parameter profile alone is
insufficient.

The example scripts compare the full output of the first prepared shot per
probability against a Scala golden using [`exactMain`](sim_main.cpp#L372).
They do not currently provide an independent all-shot correction/marginal
comparison or a sealed experiment receipt. The optional external Relay oracle
checks its supplied fixture, not the entire BB144 sweep. The
[archived result bundle](../../docs/source/experiments/bb144-results.md)
states its own verification and provenance limits.

Keep decoder selection and hardware emission in the two example directories.
Changes to physical sampling, logical definitions, or reporting belong here so
both decoders continue to receive the same benchmark contract.
