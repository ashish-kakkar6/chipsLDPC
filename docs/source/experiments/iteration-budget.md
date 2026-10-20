# BB144 iteration-budget sweep

This flow measures logical word-failure probability against average executed
BP iterations at one physical error probability. Every point reuses one sample
corpus and one maximum-capacity Verilator artifact.
The [budget run script](../../../examples/BivariateBicycle144IterationBudgetSweep/run.sh#L67)
prepares that corpus once and emits the artifact at the largest requested cap.
[`chipsldpc.plan`](../../../benchmarks/rtl_shards/adapters/chipsldpc.py#L73)
reuses each saved shard input across the requested budgets.

[Circuit model](bb144-model.md) · [Archived eight-point sweep](bb144-results.md)

The commands below use the example's general budget lists. The archived
presentation sweep used `60 120 180 300 540 1020 2040 4080` and 20,000 shots;
its settings and saved corpus are recorded on the results page.

From the repository root, run vanilla BP:

```sh
DECODER=vanilla P_VALUE=0.003 \
MAX_BP_ITERATIONS="1 2 4 8 16 32 64 128 256 512 1024" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-vanilla-budget-new 10000
```

Relay-BP-S:

```sh
DECODER=relay P_VALUE=0.003 RELAY_T0=60 RELAY_TR=60 RELAY_S=5 \
MAX_BP_ITERATIONS="60 120 180 300 540 1020 1980 3900 7740 15420 36060" \
  ./examples/BivariateBicycle144IterationBudgetSweep/run.sh \
  build/generated/bb144-relay-5-budget-new 10000
```

The [script's configuration block](../../../examples/BivariateBicycle144IterationBudgetSweep/run.sh#L8)
defines the accepted environment variables and default lists. It
[clears the selected output directory](../../../examples/BivariateBicycle144IterationBudgetSweep/run.sh#L61)
before running.

For Relay, each requested cap must be an exact whole-leg budget:

```{math}
B=T_0+RT_r,\qquad R\in\mathbb Z_{\ge0},\qquad L=R+1.
```

[`decoderRuntimeLimit`](../../../benchmarks/bb144/sim_main.cpp#L265) rejects
partial-leg or over-capacity budgets and converts $B$ to the runtime leg count
$L$. Vanilla uses $B$ directly as its runtime iteration limit.
The corresponding RTL inputs are
[`VanillaBpDecoder.iterationLimit`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L54)
and [`RelayBpDecoder.legLimit`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L65).

For completed iteration counts $I_1,\ldots,I_N$ and $F$ failed shots, the
reported coordinates and horizontal interval halfwidth are

```{math}
x=\bar I=\frac1N\sum_{k=1}^{N}I_k,\qquad
y=P_{\mathrm{word}}=\frac FN,\qquad
\Delta x=\frac{1.96s_I}{\sqrt N},
```

where $s_I$ is the sample standard deviation (`statistics.stdev`, denominator
$N-1$; the code uses zero halfwidth for $N=1$).
[`budget_report.summarize`](../../../benchmarks/bb144/budget_report.py#L14)
implements these statistics and obtains vertical confidence limits from
[`report.wilson`](../../../benchmarks/bb144/report.py#L50). The plot's x-axis
therefore measures executed work, not the cap $B$. No per-QEC-cycle
normalization is applied to its y-axis.

[`budget_report.main`](../../../benchmarks/bb144/budget_report.py#L73) checks
one probability, complete shot identities per budget, and iteration limits.
Failure flags come from
[`benchmarkMain`](../../../benchmarks/bb144/sim_main.cpp#L528); the reporter
sums those flags. It writes:

- `results/budget_sweep.csv`
- `results/budget_sweep.json`
- `results/logical_failure_vs_average_iterations.png`
- `results/logical_failure_vs_average_iterations.pdf`

At a true failure probability of $10^{-4}$, 10,000 shots give only one expected
failure. Interpret the resulting confidence interval accordingly. The
[archived results](bb144-results.md) retain their separate 20,000-shot corpus
and eight specified caps.
