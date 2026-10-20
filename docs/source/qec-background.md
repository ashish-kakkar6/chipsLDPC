# Tanner Graph and Belief Propagation background

## Decoding problem statement

A decoding problem is specified by:

- a parity check matrix $H \in \mathbb{F}_2^{M \times N}$
- an encoded logical action matrix $A \in \mathbb{F}_2^{K \times N}$
- a prior error probability vector $p = (p_0, \dots, p_{N-1})$ where error location $j$ is assumed to fail independently with probability $p_j$.

Let $e \in \mathbb{F}_2^N$ denote an unknown error on the physical qubits, and let
$\sigma \in \mathbb{F}_2^M$ be the observed syndrome:

```{math}
\sigma = H e
```

The decoding task is to infer a correction $\hat{e}$ that reproduces the syndrome
and preserves the equivalence class of the encoded logical operator:

```{math}
H \hat{e} = \sigma \qquad \text{and} \qquad A \hat{e} = A e.
```

In the examples in this repository, we work with CSS codes and 
work with split `X/Z` decoding. The syndrome is decomposed into $\sigma_X$ and
$\sigma_Z$, decoded independently using check matrices $H_X$ and $H_Z$
to obtain corrections $\hat{e}_X$ and $\hat{e}_Z$. This assumes independent $X$ and $Z$ errors and
simplifies the decoder interface.


From an assumed noise model, it is useful to construct independent binary variable priors $0 < p_j < 1$ defined via $\Pr(e_j=1)=p_j$.
One can associate to each bit a log-likelihood weight
$\omega_j = \log \frac{1-p_j}{p_j}$. The decoding problem of interest is to find the bit-wise most-likely error (MLE)
that satisfies the syndrome.

## Bit-wise MLE decoding

The full i.d.d probability distribution from the set of priors is
```{math}
:label: eq-bp-prior
\Pr_{\mathbf p}(\mathbf e)
=\prod_{j=0}^{N-1}(1-p_j)^{1-e_j} \ p_j^{e_j}.
```

The probability of obtaining a candidate error $\mathbf e$, is obtained by conditioning this probability distribution on the measured syndrome 

```{math}
:label: eq-bp-posterior
\Pr_{\mathbf p}(\mathbf e\mid\boldsymbol\sigma)
=\frac{1}{Z(\mathbf \sigma)}
  \prod_{j=0}^{N-1} (1-p_j)^{1-e_j} \  p_j^{e_j}
  \prod_{i=0}^{M-1}[H_i\mathbf e=\boldsymbol\sigma_i].
```

Here, conditioning is formally represented using Iverson notation, $[P]$ is one if $P$ is true and zero otherwise. $H_i$ denotes row (stabilizer check) $i$.
Formally, $Z(\mathbf \sigma)$ denotes the normalization of the posterior distribution, for a given syndrome $\sigma$.
To compute the probability of an error bit-wise using this posterior distribution, we need to compute bit marginal sums over the other $N-1$ components. The probability that the $j$th error bit is $b$ is obtained by summing all components of $e$ except for $j$:

```{math}
:label: eq-bp-marginal
\Pr_{\mathbf p}(e_j=b\mid\boldsymbol\sigma)
=\sum_{\mathbf e_{\sim j}\in\mathbb F_2^{N-1}}
  \Pr_{\mathbf p}(e_j=b,\mathbf e_{\sim j}\mid\boldsymbol\sigma).
```
To compute the bit-wise MLE, this marginalization needs to be done for all $N$ components of the error, and each probability maximized.
```{math}
:label: eq-bp-bit-map
\hat{\mathbf e}_{\mathrm{bit}}
=\left[
  \operatorname*{arg\,max}_{b\in\mathbb F_2}
  \Pr_{\mathbf p}(x_j=b\mid\boldsymbol\sigma)
 \right]_{j=0}^{N-1}.
```

## BP (Belief Propagation)
A direct evaluation of a single marginal requires a sum over $2^{N-1}$ assignments.
An efficient algorithm for marginalization is belief propagation, which is performed on the Tanner graph associated with $H$. The Tanner graph $G=(V,E)$ is a bi-partite graph with the two types of nodes being the variable nodes which index
columns of $H$ and check nodes which index rows of $H$. An edge exists whenever $H_{ij}=1$.

Belief propagation involves iterative message passing between check and variable nodes where each round computes a marginilization of variable nodes based on the previous rounds priors. BP is particularly an important technique for real-time decoding as it lends itself to parallelization. 
In the maximally parallel (flooding schedule), all the message passing in a single iteration can be performed in just $2$ clock cycles. 

## Local message passing and quantization

A tanner graph exposes the local priors and parity constraints in
{eq}`eq-bp-posterior`, allowing information to pass along edges.
Min-sum BP computes exact marginals on a tree and is generally approximate
on a graph with loops [1]. **chipsLDPC implements a scaled, quantized min-sum** with the following conventions for
the log-likelihood ratio (LLR)

```{math}
:label: eq-bp-llr
\Lambda_j=\log\frac{1-p_j}{p_j},\qquad
L_j=\log\frac{\Pr(e_j=0\mid\boldsymbol\sigma)}
                 {\Pr(e_j=1\mid\boldsymbol\sigma)}.
```

Larger absolute values express stronger confidence. The hardware represents
min-sum soft values as integers; hard decisions are computed via

```{math}
:label: eq-bp-hard-decision
\operatorname{HD}(z)=\begin{cases}1,&z<0,\\0,&z\ge0.\end{cases}
```
:::{admonition} Hardware
:class: author-placeholder

**Prior conversion.** Logarithms are evaluated before the RTL. For each DEM
probability $0<p_j<1/2$, the BB144 helper
[`quantize`](../../benchmarks/bb144/bb144.py#L230) computes

```{math}
\lambda_j=\min\!\left(2^{w_m}-1,\;
  \left\lfloor c\log\frac{1-p_j}{p_j}+\frac12\right\rfloor\right).
```

Here $\log$ is the natural logarithm. The conversion rounds to the nearest
integer, with half ties rounded up, then saturates.
The current [Python constants](../../benchmarks/bb144/bb144.py#L20) set
$c=2$ and $w_m=4$, so priors lie in $[0,15]$.
[`StaticDecoderInput.prior`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L9)
is unsigned and cannot carry a negative prior LLR.

**Message representation.**
[`Quantization(magnitudeBits, accumulatorBits)`](../../src/main/scala/chipsldpc/Config.scala#L3)
sets $w_m$ magnitude bits and $w_a$ signed marginal bits, with $w_a\geq w_m+1$.
[`SignMag`](../../src/main/scala/chipsldpc/Protocol.scala#L5) adds a separate sign
bit: edge-message values range from $-(2^{w_m}-1)$ to $2^{w_m}-1$.
[`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L17)
uses a wider working sum, clips the stored marginal to
$[-2^{w_a-1},2^{w_a-1}-1]$, and clips outgoing extrinsic magnitudes to
$2^{w_m}-1$. Recipient subtraction and the strict-negative hard decision happen
before marginal clipping; zero selects no correction. Shift-based check scaling
in [`Arithmetic.scale`](../../src/main/scala/chipsldpc/Arithmetic.scala#L66)
truncates each shifted term. See the {ref}`RTL arithmetic contract <bp-exact-integer>`
for the exact storage boundaries.

**Selecting a format.** Pass `q = Quantization(magnitudeBits = ..., accumulatorBits = ...)`
to [`VanillaBpConfig`](../../src/main/scala/chipsldpc/BpDecoder.scala#L7) or
[`RelayBpConfig`](../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L7).
Their defaults are `(4, 7)` and `(4, 5)`, respectively. Widths are fixed at
elaboration, so changing them requires rebuilding the RTL. Select `scale`
separately: overriding `q` does not change the default check-scaling policy.
For BB144, `PRIOR_BITS` and `PRIOR_SCALE` are source constants, not CLI options;
changing them requires regenerating the prepared priors and keeping the
Scala experiment profile, reported prior scale, and
[prior-range validation](../../src/test/scala/chipsldpc/EndToEnd.scala#L22)
consistent with the selected settings.

A larger $c$ gives finer LLR steps but reaches saturation sooner at fixed width;
different noise priors, graph degrees, Relay memory, or FPGA area/timing budgets
can therefore justify different scales and widths, checked against decoding
failure rates and hardware cost.
:::


```{figure} _static/figures/tanner-neighborhood.svg
:name: fig-tanner-neighborhood
:alt: A local Tanner neighborhood. Check i receives variable messages from j prime and j double prime, and sends sigma i j to variable j. Variable j receives messages from checks i prime and i double prime and sends R i j back to check i. The recipient's own incoming message is excluded in each outgoing update.

Check $i$ and variable $j$ share an edge. The two arrows on that edge show
opposite message directions. Other neighbors provide the inputs used when the
recipient is excluded. This is an illustrative neighborhood, not a complete
code graph.
```


In the figure, $H_{ij}=1$ gives one Tanner edge carrying two directed messages.
Check $i$ sees variable $j$ in its neighbourhood $\mathcal N(i)$; variable $j$
sees check $i$ in $\mathcal N(j)=\{i:H_{ij}=1\}$.
**$i$ is a check** and **$j$ is a variable**.
The superscript **$t$ counts completed iterations**: $t=0$ is initialization,
and the first update has $t=1$. A Tanner graph has a square check node per row of
$H$, a circular variable node per column. We outline below the quantaties necessary to define the message passing rules on a 
Tanner Graph that has been constructed from the parity check matrix coming from a stim Detector Error Model (DEM):

| Symbol                               | Meaning                                                                       | Implementation |
|--------------------------------------|-------------------------------------------------------------------------------| --- |
| $\mathbf \sigma$, $\mathbf \sigma_i$ | Measured syndrome vector and it's $i$th check bit                             | [`StaticDecoderInput.syndrome`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L8) |
| $R_{i,j}^{(t)}$                      | Variable $j$ to check $i$ message at round $t$                                | [`VariableResult.extrinsic`](../../src/main/scala/chipsldpc/Protocol.scala#L34), a vector of [`SignMag`](../../src/main/scala/chipsldpc/Protocol.scala#L5) |
| $\sigma_{i,j}^{(t)}$                 | Signed check $i$ to variable $j$ message; distinct from the **bold** syndrome | [`CheckMessage`](../../src/main/scala/chipsldpc/Protocol.scala#L25) carries minima, sign, and selector; [`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L8) reconstructs the signed value |
| $\Lambda_j$, $\lambda_j$             | Real prior Log-liklihood ratio (LLR), its quantized unsigned magnitude        | [`StaticDecoderInput.prior`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L9) receives $\lambda_j$ |
| $B_j^{(t)}$                          | Bias term applied during variable update                                      | [`StaticTannerCore.io.bias`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L96) drives [`VariableNode.prior`](../../src/main/scala/chipsldpc/VariableNode.scala#L40) |
| $M_j^{(t)}$                          | Min-sum soft value, called the marginal; saturated before storage in RTL      | [`VariableResult.marginal`](../../src/main/scala/chipsldpc/Protocol.scala#L32), registered by [`StaticVariableStage`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L40) |
| $T_j^{(t)}$                          | Full-width total before storage saturation                                    | Local `total` in [`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L8) |
| $g_t$                                | Scaling factor for check-magnitude                                     | [`Arithmetic.scale`](../../src/main/scala/chipsldpc/Arithmetic.scala#L66), configured by [`CheckScale`](../../src/main/scala/chipsldpc/Config.scala#L20) |
| $\hat e_j^{(t)}$                     | Hard decision                                     | [`Arithmetic.hardDecision(SInt)`](../../src/main/scala/chipsldpc/Arithmetic.scala#L8), returned as [`VariableResult.decision`](../../src/main/scala/chipsldpc/Protocol.scala#L33) |

:::{admonition} Hardware
:class: author-placeholder
The graph and ports are derived by [`TannerGraph.fromRows`](../../src/main/scala/chipsldpc/graph/TannerGraph.scala#L20) and [`TannerNodeGraphs.from`](../../src/main/scala/chipsldpc/graph/TannerNodeGraphs.scala#L45).
The resulting `TannerNodeGraphs.connections` supplies the check/variable port  map used by [`StaticTannerCore`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L85).
[`BpDecoderResult`](../../src/main/scala/chipsldpc/BpDecoder.scala#L23) distinguishes the selected `correction` from the final `marginal` (for RelayBP these can belong
to different legs, see [result semantics](architecture/relay-bp.md)).
:::

:::{admonition} Author text
:class: author-placeholder

[`TannerConnection`](../../src/main/scala/chipsldpc/graph/TannerNodeGraphs.scala#L5)
records these endpoints as `checkId` and `variableId`. Its `checkPort` and
`variablePort` are the positions of that edge in the two nodes' local vectors.
For example, `variableId` selects a variable node, whereas `variablePort` selects
one of that node's incident edges. The two port numbers need not be equal.
[`TannerNodeGraphs.connections`](../../src/main/scala/chipsldpc/graph/TannerNodeGraphs.scala#L30)
matches these local views using their common `edgeId`.

The [connection loop in `StaticTannerCore`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L132)
then wires `variable.result.extrinsic(edge.variablePort)` to
`check.input(edge.checkPort)`, carrying $R_{i,j}$. In the other direction, it
connects the check's shared minimum pair and that edge's `sign` and `useSecond`
fields to `variable.input(edge.variablePort)`.
[`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L10)
selects a magnitude and interprets its sign to recover $\sigma_{i,j}$.
The graph records are ordinary Scala elaboration data: the loop constructs
fixed Chisel wiring, and successive iterations update the messages over those
same connections.
:::


(bp-message-rules)=
## The three min-sum updates

In the case of Belief Propagation (or vanilla BP), we initialize the messages $R_{i,j}^{(0)}=\Lambda_j$.
[`StaticVariableStage`](../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L40) initializes each hardware edge from the unsigned input $\lambda_j$ with sign
zero. One flooding iteration updates all checks from the old variable messages, then updates all variables. In the following update rules,
$g_t$ is the check-scaling policy and $B_j^{(t)}$ is the bias. These equations expose message dependencies, the important task of
specifing their finite-width realization for Hardware is in {ref}`BP architecture’s RTL arithmetic contract <bp-exact-integer>`.

**Check to variable:** combine the syndrome bit and the other incoming signs,
then take the smallest other magnitude.

```{math}
:label: eq-bp-check-update
\sigma_{i,j}^{(t)}=
(-1)^{\boldsymbol\sigma_i\,\oplus\!
 \bigoplus_{j'\in\mathcal N(i)\setminus\{j\}}
 HD[R_{i,j'}^{(t-1)}]}
\;g_t\!\left(
 \min_{j'\in\mathcal N(i)\setminus\{j\}}
|R_{i,j'}^{(t-1)}|
\right).
```

[`CheckNode`](../../src/main/scala/chipsldpc/CheckNode.scala#L5) forms the sign from a shared XOR parity, selects a minimum from
[`TwoMinLogic.apply`](../../src/main/scala/chipsldpc/TwoMin.scala#L15), and calls [`Arithmetic.scale`](../../src/main/scala/chipsldpc/Arithmetic.scala#L66).

**Variable to check:** add the bias and message from every check except the recipient.

```{math}
:label: eq-bp-variable-update
R_{i,j}^{(t)}=B_j^{(t)}+
 \sum_{i'\in\mathcal N(j)\setminus\{i\}}\sigma_{i',j}^{(t)}.
```

[`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L8) implements this by forming one full-width total and subtracting the recipient's incoming message.

**Marginal:** include every adjacent check for the hard decision.

```{math}
:label: eq-bp-marginal-update
M_j^{(t)}=B_j^{(t)}+
 \sum_{i'\in\mathcal N(j)}\sigma_{i',j}^{(t)}.
```

The same [`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L8)calls [`Arithmetic.sum`](../../src/main/scala/chipsldpc/Arithmetic.scala#L37) to compute this total.

Vanilla BP uses $B_j^{(t)}=\Lambda_j$ in the ideal equations;
[`VanillaBpDecoder`](../../src/main/scala/chipsldpc/BpDecoder.scala#L41) wires the
quantized stored prior to `core.io.bias`. [`RelayBpDecoder`](../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L50)
instead calls [`RelayBias.apply`](../../src/main/scala/chipsldpc/RelayBias.scala#L30)
with the previous iteration's stored marginal. The [Relay architecture](architecture/relay-bp.md)
describes its rounding and memory carried between legs. Both use the same
[static BP datapath](architecture/bp-decoder.md).
Roffe et al. discuss min-sum BP in the quantum LDPC decoding setting [2].

:::{admonition} Author text
:class: author-placeholder

Consider the check-to-variable arrow $i\to j$ in the figure. At iteration $t$,
check $i$ uses $R_{i,j'}^{(t-1)}$ and $R_{i,j''}^{(t-1)}$ from the other two
variables. Their signs, together with the syndrome bit $\boldsymbol\sigma_i$,
set the outgoing sign. Min-sum takes the smaller of their magnitudes as the
check's confidence, then applies $g_t$ to obtain the outgoing magnitude.
A zero magnitude carries no preference between $e_j=0$ and $e_j=1$.
The shared parity, minimum pair and per-edge selectors in
[`CheckNode`](../../src/main/scala/chipsldpc/CheckNode.scala#L14)
implement this exclusion of the recipient's own message.

For the reverse arrow $j\to i$, variable $j$ combines its bias $B_j^{(t)}$ with
the current messages $\sigma_{i',j}^{(t)}$ and $\sigma_{i'',j}^{(t)}$.
Its full total also includes $\sigma_{i,j}^{(t)}$, which contributes to the hard
decision. To send a message back to $i$,
[`VariableLogic.apply`](../../src/main/scala/chipsldpc/VariableNode.scala#L17)
subtracts that check's contribution from the full total before packing the
outgoing sign and magnitude. Excluding the recipient in both directions avoids
immediately returning its own evidence as new information; correlations can
still return through longer loops in the graph.

The scaling policy controls the magnitude of the check's contribution relative
to the variable bias; the parity calculation determines its sign separately.
[`Arithmetic.scale`](../../src/main/scala/chipsldpc/Arithmetic.scala#L66)
implements three choices for an unsigned magnitude $a$:

- `NoScale` passes $a$ through unchanged.
- `VallsScale(r, s)` adds `a >> r` and `a >> s`, then clips the sum to the
  configured magnitude width. Each shift truncates separately.
- `RampScale(k)` computes `a - (a >> u)` for a supplied control $0\leq u\leq k$,
  and passes $a$ through for $u>k$. With increasing $u$, less is subtracted;
  the autonomous controllers start at $u=1$.

For the shifted policies, truncation happens before addition or subtraction.
Replacing these operations with a real-valued scaling followed by one rounding
step can therefore change the outgoing message. The {ref}`BP architecture <bp-cnu>`
gives the exact scaling schedule and the {ref}`RTL arithmetic contract <bp-exact-integer>`
describes how the variable update stores and clips the resulting values.
:::

[//]: # ()
[//]: # (## Post-processing)

[//]: # ()
[//]: # ([Filtered OSD-0]&#40;architecture/filtered-osd.md&#41; uses final soft values to choose)

[//]: # (a bounded, ordered set of candidate columns. It solves the restricted binary)

[//]: # (system with the [systolic GF&#40;2&#41; solver]&#40;architecture/systolic-gf2.md&#41;, then)

[//]: # (streams selected correction bits in original variable coordinates.)

[//]: # ()
[//]: # (These blocks operate on quantized hardware values. Exact behavior depends on)

[//]: # (the configured widths, scaling, truncation, saturation, graph, and stopping)

[//]: # (limits.)

## References

1. F. R. Kschischang, B. J. Frey, and H.-A. Loeliger,
   [*Factor graphs and the sum-product algorithm*](https://doi.org/10.1109/18.910572),
   *IEEE Transactions on Information Theory* **47**, 498–519 (2001).
2. J. Roffe, D. R. White, S. Burton, and E. Campbell,
   [*Decoding across the quantum low-density parity-check code landscape*](https://arxiv.org/abs/2005.07016),
   *Physical Review Research* **2**, 043423 (2020).
