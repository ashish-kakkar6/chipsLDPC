# BB144 circuit and decoding model

This page specifies the model behind the [archived BB144 results](bb144-results.md).
The experiment uses the `[[144,12,12]]` bivariate bicycle code and the circuit
schedule pinned to the
[upstream BB-code repository](https://github.com/sbravyi/BivariateBicycleCodes/tree/fa77e3333d3ec44c79d8f914dd24c040d1da471b).
It evaluates **Z-check detectors and the X-error component**, with 12 logical-Z
observables. A word is one complete 12-round memory shot across those observables.

The code parameters are $\ell=12$, $m=6$, and $a=b=(3,1,2)$.
[`bb144.upstream_config`](../../../benchmarks/bb144/bb144.py#L30) fixes these
parameters and the extraction schedule;
[`bb144.code_data`](../../../benchmarks/bb144/bb144.py#L39) constructs the CSS
check matrices and logical operators.
The physical process includes both check-extraction circuits; the decoder
receives the selected Z-check detector sector. This is a single-sector
experiment, not a combined XZ failure measurement.

:::{admonition} Author text
:class: author-placeholder

Explain why this code, circuit schedule, and sector are useful for the research
question. State which conclusions require a joint XZ experiment.
:::

## Physical noise and rounds

The circuit contains **12 noisy extraction rounds followed by two noiseless
closure rounds**. Initial data preparation and final data readout are noiseless.
The closure rounds complete the detector history; the reported per-cycle
normalization uses the 12 noisy rounds.

| Location in a noisy round | Implemented channel |
| --- | --- |
| Ancilla reset | Wrong-basis Pauli flip with probability $p$: Z after X-basis reset, X after Z-basis reset |
| Ancilla measurement | Measurement-result flip with probability $p$ |
| CNOT | Total depolarizing probability $p$; each of the 15 nonidentity two-qubit Pauli errors has probability $p/15$ |
| Explicitly scheduled data idle | Total depolarizing probability $p$; X, Y, and Z each have probability $p/3$ |

[`bb144.circuit`](../../../benchmarks/bb144/bb144.py#L63) builds the Stim circuit;
its round loop applies noise only in the first `num_cycles` rounds.
[`bb144.sample_physical`](../../../benchmarks/bb144/bb144.py#L157) implements the
corresponding Pauli-frame sampler. Idle noise is attached to the data-idle
locations in that schedule, not every qubit at every tick.

The saved shots were drawn from this **physical circuit Pauli process**. Each
shot produces detector bits and actual logical-observable flips. The actual
logical flips are retained for evaluation and are not inputs to the decoder.
In [`sample_physical.differences`](../../../benchmarks/bb144/bb144.py#L220),
successive Z-check measurements are XORed to form detectors. The following
`data_x @ lz.T` calculation gives the actual logical action.

## Detector model, matrices, and Tanner graph

The preparation flow has two related outputs:

1. The circuit's detector error model (DEM) supplies a sparse decoding matrix,
   a logical map, and prior probabilities.
2. Physical circuit sampling supplies the observed syndrome and actual logical
   action for each shot.

For the binary fault-signature vector $e$, the matrix convention is

```{math}
s=He,\qquad o=Ae,\qquad
H\in\mathbb F_2^{m\times n},\quad A\in\mathbb F_2^{12\times n}.
```

Here $m$ and $n$ count detector checks and fault signatures; they are distinct
from the code's lattice parameter $m=6$ and its 144 data qubits.

[`bb144.reduce_degree_one`](../../../benchmarks/bb144/bb144.py#L238) constructs
the sparse rows of $H$ and $A$ from each signature's detector and logical
indices. [`bb144.prepare`](../../../benchmarks/bb144/bb144.py#L307) saves their
reduced supports as `dem.row_ones` and `dem.logical_ones`.

Products are over $\mathbb F_2$. A column denotes a **detector/logical fault
signature**, which may combine effects from several physical locations. A
column does not denote one of the 144 data qubits. Equal detector supports with
different logical supports remain distinct columns. See the
[Stim DEM format](https://github.com/quantumlib/Stim/blob/main/doc/file_format_dem_detector_error_model.md)
for detector and observable semantics.

The generator requests `detector_error_model(decompose_errors=False)` and merges
identical detector/logical signatures using XOR probability:

```{math}
q_{\mathrm{merged}}=q_1(1-q_2)+q_2(1-q_1).
```

[`bb144.z_check_model`](../../../benchmarks/bb144/bb144.py#L141) selects the
Z-check sector and disables decomposition;
[`bb144.effects`](../../../benchmarks/bb144/bb144.py#L119) keys the merge by
both detector and logical indices and implements the equation above.

This is the likelihood convention used here; pinning the upstream circuit does
not establish equality with an upstream first-order likelihood calculation.
The physical shots are not sampled as independent DEM-column flips.

| Representation | Detector matrix $H$ | Logical map $A$ |
| --- | --- | --- |
| Raw merged signatures | $1008\times8856$ | $12\times8856$ |
| After exact singleton elimination | $936\times8784$ | $12\times8784$ |

The preprocessing solves 72 degree-one constraints exactly, substitutes their
values into each shot, and removes the corresponding checks and variables.
The reduced Tanner graph has **936 checks, 8,784 variables, and 30,672 edges**.
[`bb144.reduce_sample`](../../../benchmarks/bb144/bb144.py#L262) substitutes the
fixed bits into the syndrome and logical action for each shot;
[`bb144.prepare`'s dimension check](../../../benchmarks/bb144/bb144.py#L303)
enforces the reduced graph dimensions.
The physical circuit's 14 detector groups and the reduced graph's dimensions
refer to different stages of this preprocessing.

:::{admonition} Author text
:class: author-placeholder

Explain how circuit-level fault variables change the decoder's graph size and
connectivity compared with a data-qubit parity-check graph. Discuss any intended
implications for the hardware architecture.
:::

## Priors and decoder inputs

For a merged DEM probability $q_j$, the generator supplies the unsigned integer
prior

```{math}
\lambda_j=\min\!\left(15,
\left\lfloor2\ln\frac{1-q_j}{q_j}+\frac12\right\rfloor\right).
```

[`bb144.quantize`](../../../benchmarks/bb144/bb144.py#L230) implements this
rounding and clipping with `PRIOR_BITS=4` and `PRIOR_SCALE=2`; it requires
$0<q_j<1/2$.

The graph, reduced syndrome, and these priors are decoder inputs. The logical
matrix $A$ and the shot's actual observables are used by the evaluation harness.
BP in these experiments is the implemented scaled min-sum approximation.
[`CheckNode`](../../../src/main/scala/chipsldpc/CheckNode.scala#L14) computes
check parity and the two minima, using
[`Arithmetic.scale`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L66).
[`VariableLogic.apply`](../../../src/main/scala/chipsldpc/VariableNode.scala#L8)
forms the variable sums, extrinsic messages, marginal, and hard decision.
The [BP architecture guide](../architecture/bp-decoder.md) explains these
updates; the [results page](bb144-results.md) lists the saved numerical profiles.

## Failure and reported units

A converged correction must satisfy $H\hat e=s$. The benchmark counts a failure
if no syndrome-consistent correction is found **or** if any of the 12 bits of
$A\hat e$ differs from the actual logical action. Syndrome consistency alone
does not establish logical success.
[`ConvergenceChecker.residual` and `converged`](../../../src/main/scala/chipsldpc/ConvergenceChecker.scala#L13)
implement the parity test. The harness's
[`benchmarkMain` logical-action calculation](../../../benchmarks/bb144/sim_main.cpp#L528)
XORs correction bits over each logical row, compares the resulting mask with
the actual observables, and writes `logical_failure`.

For $F$ failures among $N$ complete shots,

```{math}
P_{\mathrm{word}}=\frac{F}{N},\qquad
q_{\mathrm{equiv}}=1-(1-P_{\mathrm{word}})^{1/12}.
```

[`report.summarize`](../../../benchmarks/bb144/report.py#L99) sums the harness's
saved `logical_failure` flags and divides by the shot count.
[`report.per_qec_cycle`](../../../benchmarks/bb144/report.py#L59) implements the
normalization; [`report.main`](../../../benchmarks/bb144/report.py#L383) obtains
the denominator 12 from `sweep.code.cycles`.

The probability-sweep figures use $q_{\mathrm{equiv}}$, a constant-hazard
equivalent per noisy QEC cycle. It is not a direct count of failures in
individual cycles or logical qubits. The iteration-budget figure uses the
untransformed $P_{\mathrm{word}}$. Two-sided Wilson 95% intervals describe the
word-failure estimate. [`report.wilson`](../../../benchmarks/bb144/report.py#L50)
uses $z=1.959963984540054$; `report.summarize` transforms both interval endpoints
with the same function as the estimate.
[`budget_report.summarize`](../../../benchmarks/bb144/budget_report.py#L14)
retains the untransformed word probability and computes the mean executed
iterations and its $1.96s/\sqrt N$ halfwidth.

:::{admonition} Author text
:class: author-placeholder

State the scientific question addressed by each rate convention. Explain which
finite-sample conclusions the figures support and what additional measurements
would be needed for threshold, latency, or full-code claims.
:::
