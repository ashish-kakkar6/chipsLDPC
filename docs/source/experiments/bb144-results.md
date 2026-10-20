# Archived BB144 results

These three figures reproduce the **22 saved records** used by the Beamer
results presentation: seven vanilla-BP points, seven Relay-BP points, and eight
Relay-BP budget points. No simulation was rerun to create these figures.
The [circuit and decoding model](bb144-model.md) defines the physical noise,
matrix dimensions, failure classification, and plotted units.

The `legacy-v1` bundle is a documentation label for these archived records.
The original sweep metadata uses schema `chipsldpc.bb144.v2`; it does not
contain a sampler-version field. The bundle retains exact CSV bytes and
SHA256 identities, original decoder configurations, selected source metadata,
and simulation-run summaries.
The schema is written by
[`bb144.prepare`](../../../benchmarks/bb144/bb144.py#L307). The frozen files
below identify the archived experiments; links to implementation symbols refer
to the current checkout and do not establish its identity as the original
experiment producer.

## Saved profiles

| Setting | Vanilla BP | Relay-5 probability sweep | Relay-5 budget sweep |
| --- | --- | --- | --- |
| Physical $p$ | .001, .002, …, .007 | .001, .002, …, .007 | .003 |
| Shots per point | 1,000 | 1,000 | 20,000 |
| Initial-leg cap $T_0$ | 30 | 80 | 60 |
| Later-leg cap $T_r$ | — | 60 | 60 |
| Additional legs $R$ | — | 600 | 0, 1, 2, 4, 8, 16, 33, 67 |
| Solution target $S$ | First convergence | 5 | 5 |
| Message magnitude bits | 4, plus sign | 4, plus sign | 4, plus sign |
| Signed marginal bits | 7 | 5 | 5 |
| Root sampling seed | 14412 | 14412 | 14412 |

The saved [vanilla configuration](../_static/bb144-results/legacy-v1/vanilla-config.json),
[Relay configuration](../_static/bb144-results/legacy-v1/relay-config.json), and
[budget configuration](../_static/bb144-results/legacy-v1/budget-config.json)
are the authority for this table.
[`RelayDefaults.q`, `paperQ`, and `paperFormat`](../../../src/main/scala/chipsldpc/Config.scala#L8)
define the corresponding arithmetic profiles in the current implementation.

Each BP leg stops at convergence or its iteration cap. Relay returns the
lowest-prior-score converged candidate, retaining the earlier candidate on a
tie; it stops at $S$ converged candidates or the leg limit. $R$ counts legs
**after** the initial leg. The probability-sweep cap is therefore
$80+600\times60=36{,}080$ iterations. The budget sweep uses

```{math}
B=T_0+RT_r=60(R+1),\qquad R\in\{0,1,2,4,8,16,33,67\}.
```

[`RelayBpExperimentProfile.decoderConfig`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L25)
maps $R$ to `maximumLegs = R + 1`;
[`RelayBpConfig.maximumIterations`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L25)
computes the cap above.
[`RelayBpDecoder.candidateWins`, `legDone`, and `targetReached`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L112)
implement candidate selection and early stopping. Vanilla's corresponding
stop/result branch is in
[`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L84).

Both Relay profiles use `int4.2.8`, coefficient scale 8, initial integer
coefficient 7, later coefficients 3 through 10, and seed offset zero. The
per-variable 16-bit Galois coefficient generator is deterministic and reseeds
each frame. Its quantized effective $\gamma$ values range from $-0.25$ to
$0.625$; the configured requested interval is $[-0.24,0.66]$. These settings
reference the [FPGA study's parameter profile](https://arxiv.org/abs/2510.21600),
not equivalence to its coefficient generator or its full XZ dataset.
[`LfsrRelayCoefficients`](../../../src/main/scala/chipsldpc/RelayCoefficients.scala#L38)
implements frame reseeding and leg advances;
[`RelayBpExperiment.writeConfig`](../../../src/test/scala/chipsldpc/RelayBpExperiment.scala#L187)
records the integer coefficients and requested/effective $\gamma$ intervals.

The vanilla and Relay probability sweeps use identical saved physical input
bodies, with different iteration headers. They compare complete decoder
profiles: arithmetic width, budget, and stopping target also differ. The budget
sweep uses a separate physical corpus; every budget within that sweep shares
the same 20,000 shots.

## Vanilla BP

:::{figure} ../_static/bb144-results/legacy-v1/vanilla-rate.svg
:alt: Vanilla BP equivalent per-cycle failure across seven physical probabilities from 0.1 to 0.7 percent, with Wilson 95 percent intervals.

Vanilla scaled min-sum BP, capped at 30 iterations, with 1,000 shots at each
probability. The y-axis is $q_{\mathrm{equiv}}=1-(1-P_{\mathrm{word}})^{1/12}$.
Vertical intervals are the transformed Wilson 95% intervals. All recorded
failures in this saved vanilla sweep are nonconvergence failures.
:::

The transform is implemented by
[`report.per_qec_cycle`](../../../benchmarks/bb144/report.py#L59), and the
interval by [`report.wilson`](../../../benchmarks/bb144/report.py#L50).

:::{admonition} Author text
:class: author-placeholder

Interpret the vanilla curve. Discuss what the observed behavior suggests about
this numerical profile and iteration limit, without treating the seven points
as a threshold estimate.
:::

## Relay BP

:::{figure} ../_static/bb144-results/legacy-v1/relay-rate.svg
:alt: Relay-5 equivalent per-cycle failure across seven probabilities; the first two points are zero-failure upper bounds, and the five positive estimates have Wilson intervals.

Relay-5 with $T_0=80$, $T_r=60$, $R=600$ and 1,000 shots per point. The y-axis
has the same equivalent per-cycle definition as the vanilla figure. At
$p=.001$ and $.002$, zero observed failures are drawn as separate downward
triangles at the upper Wilson 95% bound; they are not positive estimates or
connected to the estimate curve. Failure includes both nonconvergence and
logical mismatches among converged outputs.
:::

[`report.plot_rate`](../../../benchmarks/bb144/report.py#L187) separates zero
counts from positive estimates. The archived documentation renderer uses the
same marker rule in [`publish_bb144.render`](../../figures/publish_bb144.py#L138).

:::{admonition} Author text
:class: author-placeholder

Compare the complete vanilla and Relay profiles. Separate the measured
difference from claims about the cause; discuss the differing widths, work
budgets, stopping rules, and limits of the zero-failure observations.
:::

(relay-budget-results)=
## Relay iteration-budget sweep

:::{figure} ../_static/bb144-results/legacy-v1/relay-budget.svg
:alt: Eight Relay-5 budget points labeled by additional-leg count R, showing word-failure probability against measured mean executed BP iterations at physical probability 0.3 percent.

Relay-5 on the BB144 Z-check sector at $p=0.003$, $T_r=60$, $S=5$ and
20,000 shots per budget. Point labels give the additional relay legs $R$.
The x-axis is the **mean executed** iteration count, and the y-axis is
word-failure probability.
:::

[`budget_report.summarize`](../../../benchmarks/bb144/budget_report.py#L14)
computes the plotted statistics. The harness's
[`decoderRuntimeLimit`](../../../benchmarks/bb144/sim_main.cpp#L265) converts
each total cap to a runtime leg count;
[`checkRelayTiming`](../../../benchmarks/bb144/sim_main.cpp#L283) checks the
executed leg/iteration counts and two-clock iteration timing.

:::{admonition} Author text
:class: author-placeholder

Discuss the observed reliability/work tradeoff. Distinguish average executed
work from worst-case budget, and identify the latency-tail or hardware timing
measurements needed to extend this result.
:::

## Data, provenance, and verification scope

| Bundle item | Downloads |
| --- | --- |
| Vanilla | [CSV](../_static/bb144-results/legacy-v1/vanilla.csv), [decoder config](../_static/bb144-results/legacy-v1/vanilla-config.json), [run summary](../_static/bb144-results/legacy-v1/vanilla-run.json) |
| Relay | [CSV](../_static/bb144-results/legacy-v1/relay.csv), [decoder config](../_static/bb144-results/legacy-v1/relay-config.json), [run summary](../_static/bb144-results/legacy-v1/relay-run.json) |
| Budget | [CSV](../_static/bb144-results/legacy-v1/budget.csv), [decoder config](../_static/bb144-results/legacy-v1/budget-config.json), [run summary](../_static/bb144-results/legacy-v1/budget-run.json) |
| Dataset identity | [Manifest](../_static/bb144-results/legacy-v1/manifest.json), [selected metadata](../_static/bb144-results/legacy-v1/metadata.json), [original presentation provenance](../_static/bb144-results/legacy-v1/presentation-provenance.json) |
| Figure identity | [Rendering receipt](../_static/bb144-results/legacy-v1/figures.json); PNG alternatives: [vanilla](../_static/bb144-results/legacy-v1/vanilla-rate.png), [Relay](../_static/bb144-results/legacy-v1/relay-rate.png), [budget](../_static/bb144-results/legacy-v1/relay-budget.png) |

The saved runs have first-shot verification fixtures, but their summary/raw
outputs do not provide an all-shot full-vector audit, producer receipts, a
sealed experiment receipt, or a recoverable original producer-source revision.
This lightweight bundle does not contain raw shots, benchmark bodies, complete
sparse matrices, RTL, or simulator binaries. The manifest records the original
summary CSV, decoder configuration, run summary, `sweep.json`, and
`benchmark.txt` paths and hashes. It does not bind the original raw-shot CSV,
RTL, or executable. Those source paths identify local archives; they are not
download links or evidence of a complete release.

The historical sampler used `numpy.default_rng(seed + probability_index)`
with sequential array draws. Corpus identity depends on probability ordering
and shot count as well as the seed. The original metadata records Stim 1.16.0
but omits NumPy and other numerical-package versions. Rebuilding a current
profile is a new experiment unless its actual input corpus and output records
are checked against the archive. A figure checksum establishes file identity,
not decoder correctness.
The corresponding current implementation is
[`bb144.prepare`'s `seed + index` call](../../../benchmarks/bb144/bb144.py#L290)
and [`bb144.sample_physical`'s RNG](../../../benchmarks/bb144/bb144.py#L165).

For new runs, [`bb144.prepare`](../../../benchmarks/bb144/bb144.py#L279) writes
`z_checks.stim` only for the first probability, while writing a DEM per point.
That circuit text is not a complete circuit archive for a sweep. Stim's text
serialization can round very close probability values, so retain the saved
sample corpus and exact probability arguments rather than treating the printed
circuit alone as the sampler's full specification.

## Check and redraw the frozen figures

From the repository root, the checker uses only the Python standard library:

```sh
python3 docs/figures/publish_bb144.py --check
```

It validates all 22 records against the frozen CSV hashes, profile settings,
failure fractions, Wilson intervals, per-cycle transformations, R/budget mapping,
and saved figure hashes. The horizontal mean intervals are preserved and
hash-checked; their raw iteration samples are not in this bundle.
[`publish_bb144.check_inputs`](../../figures/publish_bb144.py#L53) validates the
inputs and formulas; [`check_figures`](../../figures/publish_bb144.py#L128)
validates the renderer and image identities.

To redraw with the benchmark environment's Matplotlib installation:

```sh
MPLCONFIGDIR=/tmp/chipsldpc-mpl .venv/bin/python docs/figures/publish_bb144.py --render
python3 docs/figures/publish_bb144.py --check
```

[`publish_bb144.main`](../../figures/publish_bb144.py#L208) reads only
the checked-in bundle and writes its SVG/PNG figures and rendering receipt.
It does not prepare circuits, run decoders, or read a sibling presentation.
The ordinary documentation build consumes the committed images.

For new simulations, use the [BP-only](bp-only.md), [Relay-BP](relay-bp.md), and
[iteration-budget](iteration-budget.md) workflows with fresh output directories
and explicit settings. The run scripts clear their selected output directories;
keep the historical archives separate. Recorded simulation-only wall times
were about four minutes for vanilla, eleven hours for Relay, and 4.1 hours for
the budget sweep on 16 workers. These are host execution measurements, excluding
build time; they are not hardware latency or portable runtime estimates.
