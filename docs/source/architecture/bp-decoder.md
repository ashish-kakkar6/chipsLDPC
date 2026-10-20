# BP decoder

[`StaticTannerCore`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L85)
is the shared fixed-graph min-sum network.
[`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L41)
adds its autonomous early-terminating controller.

## Static Tanner network

[`TannerGraph.fromRows`](../../../src/main/scala/chipsldpc/graph/TannerGraph.scala#L20)
builds the graph from the nonzero column indices of each parity-check row.
[`TannerNodeGraphs.from`](../../../src/main/scala/chipsldpc/graph/TannerNodeGraphs.scala#L45)
derives local CNU and VNU ports from its stable, row-major edge identifiers.
Rows are sorted by variable index; duplicate or out-of-range entries, empty
checks, and unused variables are rejected. The graph representation permits
degree-one checks, but
[`StaticTannerCore`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L91)
requires every check to have degree at least two. Variable degree one is valid.

`StaticTannerCore` instantiates:

- one `StaticCheckStage` for each parity check;
- one `StaticVariableStage` for each variable;
- one fixed connection for every graph edge; and
- one combinational
  [`ConvergenceChecker`](../../../src/main/scala/chipsldpc/ConvergenceChecker.scala#L7) for
  $H\hat{\mathbf e} + \boldsymbol\sigma$ over $\mathrm{GF}(2)$.

An accepted `load` stores the syndrome and unsigned quantized priors $\lambda_j$.
[`StaticVariableStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L60)
initializes $M_j=\lambda_j$, $R_{i,j}=+\lambda_j$, and $\hat e_j=0$.

An accepted `step` starts one iteration. All check stages update on the first
clock and all variable stages commit on the second. The immediate `commit`
view is used by autonomous controllers;
[`StaticTannerDatapath`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L168)
exposes the registered `result` view. The phase enables and fixed edge wires
are constructed by
[`StaticTannerCore`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L103);
there is no row-by-row runtime schedule.

## From messages to RTL

Check $i$ and variable $j$ exchange $R_{i,j}$ (variable to check) and
$\sigma_{i,j}$ (check to variable). The measured syndrome is
$\boldsymbol\sigma$; $\mathcal N(i)$ and $\mathcal N(j)$ denote the neighbors
of the indicated node. The [QEC background](../qec-background.md) introduces
these messages. Here the equations describe the quantized hardware values;
the links beside them identify their production implementation.

:::{admonition} Author text
:class: author-placeholder

Explain the transition from the min-sum equations to shared arithmetic. Introduce
which quantities are reused across all edges and which remain specific to one
recipient. Relate the two diagrams below to a local Tanner neighborhood.
:::

(bp-cnu)=
### CNU: shared parity and minima

```{figure} ../_static/figures/cnu.svg
:alt: CNU sign and magnitude paths share a parity reduction and two minima; a result register stores the pair and per-edge sign and selector.
:width: 100%

One check's combinational arithmetic and its static-stage register. The diagram
shows one representative edge's sign and selector; those fields exist for every
neighbor. The scaled minimum pair is shared.
```

Suppress iteration labels within one update. Canonical input signs and the
syndrome-adjusted shared parity are

```{math}
b_{i,j}=[R_{i,j}<0],\qquad
P_i=\boldsymbol\sigma_i\oplus\bigoplus_{j\in\mathcal N(i)}b_{i,j},\qquad
s_{i,j}=P_i\oplus b_{i,j}.
```

[`Arithmetic.hardDecision`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L9)
canonicalizes input signs, and
[`CheckNode.parity`](../../../src/main/scala/chipsldpc/CheckNode.scala#L15)
forms the shared XOR.
[`CheckNode.result.edges`](../../../src/main/scala/chipsldpc/CheckNode.scala#L23)
then XORs each recipient's sign
out of that parity.

Let $a_{i,1}\le a_{i,2}$ be the two smallest input magnitudes **with
multiplicity**. The CNU scales the pair once and compares each input against the
*raw* first minimum:

```{math}
m_{i,k}=g_t(a_{i,k}),\quad k\in\{1,2\},\qquad
c_{i,j}=[|R_{i,j}|=a_{i,1}].
```

[`TwoMinLogic.apply`](../../../src/main/scala/chipsldpc/TwoMin.scala#L15)
computes the pair. [`CheckNode`](../../../src/main/scala/chipsldpc/CheckNode.scala#L16)
scales it once and assigns the per-edge `useSecond` comparison.

The VNU reconstructs the exclusive check message using that selector:

```{math}
\sigma_{i,j}=(-1)^{s_{i,j}}
\begin{cases}
m_{i,2},&c_{i,j}=1,\\
m_{i,1},&c_{i,j}=0.
\end{cases}
```

[`VariableLogic.apply`](../../../src/main/scala/chipsldpc/VariableNode.scala#L10)
selects the magnitude and
[`Arithmetic.fromSignMag`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L11)
interprets its sign. Duplicate minima remain valid: $(2,2,5)$ produces $(2,2)$,
so both tied edges can select the second value. A zero magnitude is numerically
zero regardless of its metadata sign.

[`CheckResult`](../../../src/main/scala/chipsldpc/Protocol.scala#L20)
stores one `MinPair` and a vector of `EdgeMeta(sign, useSecond)`:
$2w_m+2d_c$ result bits for check degree $d_c$, excluding the stored syndrome.
[`CheckMessage`](../../../src/main/scala/chipsldpc/Protocol.scala#L25)
is the VNU-side wire view of that pair and one edge's metadata; it does not imply
a separately registered pair on each edge. The static core requires $d_c\geq2$.

Available scaling policies are:

- `NoScale`: preserve the magnitude;
- `VallsScale(a, b)`: `(x >> a) + (x >> b)`, clipped to the magnitude width;
- `RampScale(maxShift)`: `x - (x >> u)` for controls through `maxShift`, then
  `x`.

[`Arithmetic.scale`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L66)
implements these policies. For `RampScale(k)`, the exact control-dependent rule is

```{math}
g_u(a)=\begin{cases}
a-\lfloor a/2^u\rfloor,&0\leq u\leq k,\\
a,&u>k.
\end{cases}
```

This subtracts a truncated shifted value; it does not round the complete
real-valued product downward. The autonomous
[`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L62)
and [`RelayBpDecoder`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L99)
start local iteration $t$ at one and supply $u=\min(t,2^{w_u}-1)$.
[`RampScale.controlBits`](../../../src/main/scala/chipsldpc/Config.scala#L27)
defines $w_u$; the maintained default is `RampScale(4)`.
The manual datapath takes $u$ directly from `step.bits`. In particular, $u=0$
sets both scaled minima to zero; autonomous controllers begin at $u=1$.

:::{admonition} Author text
:class: author-placeholder

Explain why shared parity and a duplicate-preserving two-minimum tree avoid
separate reductions for every outgoing edge. Discuss the source-level storage
and fanout tradeoff without asserting a placed-and-routed area or delay result.
:::

(bp-vnu)=
### VNU: one total, three outputs

```{figure} ../_static/figures/vnu.svg
:alt: The VNU selects and signs incoming CNU magnitudes, adds them to the bias, and sends the full total to subtraction, saturation, and hard-decision branches.
:width: 100%

The full-width total feeds every output branch. Per-edge subtraction bypasses
the stored marginal's saturation. The drawing shows an ordinary iteration;
at a Relay leg transition the edge-message register instead reloads the prior,
as described below.
```

(bp-exact-integer)=
### Where the RTL contract differs from ideal arithmetic

[`VariableLogic.apply`](../../../src/main/scala/chipsldpc/VariableNode.scala#L8)
reconstructs signed check messages, adds the bias, and reuses one
total for the marginal, hard decision, and every outgoing extrinsic message:

```{math}
:label: eq-bp-integer-boundary
\begin{aligned}
T_j&=B_j+\sum_{i\in\mathcal N(j)}\sigma_{i,j},\\
M_j&=\operatorname{sat}_{w_a}(T_j),\qquad
\hat e_j=[T_j<0],\\
R_{i,j}&=\operatorname{pack}_{w_m}(T_j-\sigma_{i,j}).
\end{aligned}
```

Here $T_j$ is the full working-width sum and $M_j$ the stored signed marginal.
[`Arithmetic.clipSigned`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L16)
implements `sat` on $[-2^{w_a-1},2^{w_a-1}-1]$;
[`Arithmetic.toSignMag`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L28)
implements `pack`, clipping magnitude to $2^{w_m}-1$ and canonicalizing zero.
Subtraction and decision occur **before** clipping the stored marginal.
[`Arithmetic.hardDecision`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L8)
selects zero for $T_j=0$.

[`Arithmetic.sum`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L37)
uses a balanced tree padded to
$w_a+\max(1,\operatorname{bitlength}(|\mathcal N(j)|))$ bits, as derived by
[`VariableConfig.workBits`](../../../src/main/scala/chipsldpc/Config.scala#L36).
[`Quantization`](../../../src/main/scala/chipsldpc/Config.scala#L3)
requires $w_a\geq w_m+1$. A bias lies in the signed $w_a$-bit range, while each
check message has magnitude at most $2^{w_m}-1$. These bounds fit both the
working sum and the subsequent recipient subtraction without arithmetic wrap.

Vanilla drives $B_j$ from the immutable prior; {ref}`Relay <relay-memory>`
computes $B_j$ from the prior and the previous stored marginal.
[`StaticVariableStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L55)
connects this bias to the leaf port named `VariableNode.prior`; that port is the
current bias, not necessarily the immutable frame prior.

On a normal VNU commit, the stage stores all three calculated outputs.
When Relay asserts `restartMessages` at a leg boundary,
[`StaticVariableStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L67)
still stores the newly calculated $M_j$ and $\hat e_j$, but stores
$R_{i,j}=+\lambda_j$ for the next leg instead of the calculated extrinsic message.
The immutable prior is not reloaded from the external input at that boundary.

:::{admonition} Author text
:class: author-placeholder

Explain why total-minus-own implements the recipient exclusion in the variable
update. Relate one incident edge's incoming check message, bias, full total, and
outgoing message. Explain why subtracting
from an already saturated marginal would change the result.
:::

### Clock and initialization boundaries

The arithmetic leaves are combinational `RawModule`s.
[`StaticCheckStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L30) stores
the syndrome on `load` and the CNU result on `step.fire`. `StaticVariableStage`
commits the next marginal, decision, and edge messages on the following VNU
phase, subject to the Relay restart override above. The autonomous controllers
first test convergence after a completed iteration, including when the loaded
syndrome is zero.

For the manually stepped
[`StaticTannerDatapath`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L175),
`load` and `step` use ready/valid handshakes. Before the first accepted load,
`step.ready` is false. A pending `load.valid` has priority over a step;
neither request can be accepted during the VNU phase. Its `result` is a
**one-cycle `Valid` pulse**, with no `ready` signal or output backpressure.
Consumers must sample the registered snapshot while `result.valid` is high.

[`StaticTannerCore.commit`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L154)
uses the combinational next VNU decisions for convergence on the VNU phase;
`result` exposes the registered snapshot afterward. The two-clock schedule
describes decoder computation, not input/output transport latency or an achieved
FPGA clock frequency.

For the published CNU and VNU datapath schematics, see
[Maurer et al., Sec. 4.1, Fig. 3(a–b)](https://arxiv.org/abs/2510.21600).
The diagrams above make the current chipsLDPC bundle and register boundaries
explicit; the linked Scala sources define their implemented behavior.

## Autonomous vanilla BP

[`VanillaBpConfig`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L7)
requires a positive iteration limit and fixes the graph, quantization, and check
scaling. [`RelayDefaults.q`](../../../src/main/scala/chipsldpc/Config.scala#L10)
supplies four magnitude bits and seven signed marginal bits;
[`RelayDefaults.scale`](../../../src/main/scala/chipsldpc/Config.scala#L11)
supplies the default ramp policy.

[`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L78)
accepts `StaticDecoderInput` through `io.in`. It runs until
the residual is zero or the frame limit is reached, then holds a
[`BpDecoderResult`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L23)
on `io.out` until accepted. The result contains:

- success and correction bits;
- final signed marginals and residual;
- completed iterations; and
- `legsExecuted = 1` and `solutionsFound` equal to the success flag.

When `runtimeIterationLimit` is elaborated, the optional limit port may select
any positive prefix of the configured capacity; it is sampled on `io.in.fire`.
For $N$ completed iterations, `io.out.valid` first becomes high immediately
after the $2N$th rising clock edge **following** the accepted input edge.
This excludes the edge that accepts the result through `io.out.fire`.
Output backpressure extends interface latency but does not alter the reported
iteration count. A new input cannot be accepted until the current output has
been accepted and the controller has returned to its idle state.

## Inspect and test

```sh
./scripts/emit.sh static-steane
./scripts/emit.sh vanilla-steane
./mill chipsLDPC.test.testOnly chipsldpc.TwoMinSpec chipsldpc.CheckNodeSpec chipsldpc.VariableNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.StaticTannerDatapathSpec
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
```

The maintained large experiment is in `examples/BivariateBicycle144BpOnly/`.
Relay control is described in [Relay BP](relay-bp.md).
