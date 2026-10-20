# Relay BP

[`RelayBpDecoder`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L50)
runs Relay-BP-S over the same static Tanner network as vanilla BP. It changes
the VNU bias and controller state; it does not duplicate the graph datapath.

(relay-memory)=
## Bias with memory

Let $\ell$ index a leg, $t$ the iteration inside that leg, and $j$ a variable.
The **ideal real-valued** bias mixes immutable prior $\Lambda_j$ with the previous
marginal $M_j^{(\ell,t-1)}$:

```{math}
\begin{aligned}
B_j^{(\ell,t)}&=(1-\gamma_{\ell,j})\Lambda_j
  +\gamma_{\ell,j}M_j^{(\ell,t-1)},\\
\bar\beta_{\ell,j}&=1-\gamma_{\ell,j}=b_{\ell,j}/2^f.
\end{aligned}
```

The coefficient is fixed within a leg; the previous marginal changes at every
iteration. Vanilla BP is the ideal special case $\gamma=0$.
[`RelayBpDecoder`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L89)
connects the immutable prior, the previous **stored, saturated** marginal, and
the current coefficient to `RelayBias`. The integer operations below define
the actual bias; the real-valued equation describes its motivation.

:::{admonition} Author text
:class: author-placeholder

Introduce why Relay changes the bias while retaining the same CNU/VNU message
updates. Explain the distinct roles of iteration-to-iteration memory and
leg-to-leg coefficient changes, using the notation above. Discuss the motivation
and scope of the method with the original Relay reference.
:::

### Exact fixed-point realization

Let $w_m$ and $w_a$ be `Quantization.magnitudeBits` and
`Quantization.accumulatorBits`, and $f$ be `RelayFormat.fractionalBits`; see
[`Quantization`](../../../src/main/scala/chipsldpc/Config.scala#L3) and
[`RelayFormat`](../../../src/main/scala/chipsldpc/Config.scala#L39).
Write $\lambda_j$ for the quantized unsigned prior, with
$0\leq\lambda_j\leq2^{w_m}-1$ as carried by
[`StaticDecoderInput.prior`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L9).
[`StaticVariableStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L60)
loads $M_j^{(0,0)}=\lambda_j$ and $R_{i,j}^{(0,0)}=+\lambda_j$.
For unsigned coefficient integer $b$ and $f$ fractional bits, write
$|x|=\sum_r x_r2^r$. The reduced product and implemented bias are

```{math}
\begin{aligned}
\rho_f(x,b)&=\epsilon(x)\sum_{r=0}^{w_a-1}
  x_r\left\lfloor\frac{b2^r}{2^f}\right\rfloor,
\qquad \epsilon(x)=\begin{cases}-1,&x<0,\\+1,&x\geq0,\end{cases}\\
B_j^{(\ell,t)}&=\operatorname{sat}_{w_a}\!\left(
  \rho_f(\lambda_j,b_{\ell,j})+M_j^{(\ell,t-1)}
  -\rho_f(M_j^{(\ell,t-1)},b_{\ell,j})\right).
\end{aligned}
```

[`RelayBias.reducedMultiply`](../../../src/main/scala/chipsldpc/RelayBias.scala#L8)
implements $\rho_f$: it truncates each magnitude partial product before
addition and restores the sign. [`RelayBias.apply`](../../../src/main/scala/chipsldpc/RelayBias.scala#L30)
evaluates the two products separately and clips the mixed result with
[`Arithmetic.clipSigned`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L16).
For example, $\rho_3(15,7)=11$, whereas multiplying first and
then truncating gives $\lfloor15\cdot7/8\rfloor=13$. The two reduced products
cannot in general be replaced by one reduced product of $\lambda_j-M_j$.
The partial-product truncation follows
[Maurer et al., Appendix C, Table 2](https://arxiv.org/html/2510.21600v1).

[`RelayDefaults.paperQ`](../../../src/main/scala/chipsldpc/Config.scala#L16)
and [`RelayDefaults.paperFormat`](../../../src/main/scala/chipsldpc/Config.scala#L17)
set four magnitude bits, five signed marginal bits, and a four-bit coefficient
with three fractional bits. Vanilla's maintained
default uses seven marginal bits, so a comparison between the default profiles
does not isolate the effect of Relay memory alone.

### Coefficients within a leg

The default
[`LfsrRelayCoefficients`](../../../src/main/scala/chipsldpc/RelayCoefficients.scala#L38)
contains one deterministic 16-bit Galois LFSR per
variable. Its [`io.frameStart`](../../../src/main/scala/chipsldpc/RelayCoefficients.scala#L51)
branch restores integer $b=7$, meaning $\bar\beta=7/8$ and
$\gamma=1/8$. Each later leg advances every LFSR once and maps the **new state's** low bits
to integers $3,\ldots,10$. Thus $\gamma\in[-1/4,5/8]$ for the default format;
the ideal expression is not always a convex mixture. Coefficients stay constant
within a leg, and each accepted frame restores the same initial state. This is
a deterministic schedule, not independent random draws.
[`LfsrRelayCoefficients.laneSeed`](../../../src/main/scala/chipsldpc/RelayCoefficients.scala#L24)
defines each lane's initial state; the
[`io.advanceLeg`](../../../src/main/scala/chipsldpc/RelayCoefficients.scala#L54)
branch applies the Galois recurrence and coefficient mapping. An explicit
[`RelayBpDecoder.coefficientFactory`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L80)
can replace this source while retaining the controller-facing interface.

(relay-legs)=
## Leg control

```{figure} ../_static/figures/relay-legs.svg
:alt: Relay loads a frame, runs BP with fixed coefficients inside each leg, carries stored marginals into later legs, and selects the lowest-score converged candidate.
:width: 100%

The terminal stored marginal carries memory forward. A new leg restarts its
edge messages and local scaling while advancing the coefficient source.
```

[`RelayBpConfig`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L7)
defaults to `initialIterations = 80`, `relayIterations = 60`,
`maximumLegs = 600`, `solutionTarget = 1`, and `seedOffset = 0`.
[`RelayBpDecoder.legBudget`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L96)
uses the initial budget for leg zero and the relay budget thereafter. A leg ends
early on a zero residual. At a leg boundary:

- signed marginals remain available as memory;
- edge messages restart from immutable positive priors;
- the local scaling schedule restarts; and
- coefficient generators advance for the next leg.

These changes occur on the terminal VNU commit and add no controller clock.
[`RelayBpDecoder.advanceLeg`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L119)
drives message restart and coefficient advancement on that commit;
[`StaticVariableStage`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala#L67)
retains the new marginal while replacing the outgoing messages with priors.
The controller resets its local iteration counter for the next ramp.
`maximumLegs` counts all hardware legs, including leg zero.

Relay stops after `solutionTarget` syndrome-consistent candidates or the frame
leg limit. Candidate score is the sum of immutable prior magnitudes at asserted
correction positions:

```{math}
Q(\hat{\mathbf e})=\sum_j\lambda_j\hat e_j.
```

[`RelayBpDecoder.candidateScore`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L111)
implements this score with [`Arithmetic.sumUnsigned`](../../../src/main/scala/chipsldpc/Arithmetic.scala#L48).
Here $\lambda_j$ is the **quantized integer prior**. The lowest score wins; an
equal score keeps the earlier candidate. Identical corrections count again
toward the solution target: `candidateWins` uses a strict comparison, while
`nextSolutions` counts each convergence event. This score selects individual consistent candidates;
it is not a sum of probabilities over a quantum logical class.

:::{admonition} Author text
:class: author-placeholder

Walk through a leg boundary: identify what persists, what restarts, and what
changes. Explain the distinction between requesting several convergence events
and finding several distinct corrections. Connect the candidate rule to the
decoding objective without equating syndrome consistency with logical success.
:::

[`RelayBpDecoder.io.legTrace`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L126)
emits a nonblocking event at each terminal leg commit. It reports
the zero-based leg index, local iterations, and convergence flag. From the
accepted input edge to the first asserted `io.out.valid`, a frame takes exactly
twice its total BP iterations in decoder clocks; leg transitions add none.
Convergence is checked after VNU updates, so every accepted frame runs at least
one iteration, including a frame with zero syndrome. Waiting for the output
consumer adds interface latency without adding BP iterations.

## Result semantics

[`RelayBpDecoder.outcome`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L163)
captures a [`BpDecoderResult`](../../../src/main/scala/chipsldpc/BpDecoder.scala#L23)
for `io.out`:

- `success` means at least one syndrome-consistent candidate, even if the leg
  limit ended the run before the requested solution count was reached;
- `correction` is the best consistent candidate, or the final decision if none
  converged;
- `marginal` is always the final leg's soft state;
- `residual` is zero when a consistent candidate exists, otherwise it accompanies
  the final decision;
- `solutionsFound`, `legsExecuted`, and `totalIterations` report completed
  work; and
- failure returns the final leg's coherent correction and residual snapshot.

The selected correction may come from an earlier leg than the final marginals.
Do not reconstruct that correction from the signs of the returned marginals.
Logical correctness requires a separate observable check.

When [`RelayBpDecoder.legLimit`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala#L65)
is elaborated, the input handshake captures a positive prefix of the configured
leg capacity. `io.out` holds its result until accepted; output stalls do not
change iteration counts.

## Inspect and test

```sh
./scripts/emit.sh relay-steane
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayBiasSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayCoefficientsSpec
```

[`BpDecodersSpec`](../../../src/test/scala/chipsldpc/BpDecodersSpec.scala#L231)
includes matching-profile equivalence to vanilla at integer
$b=8$, message restarts, candidate replacement, equal-score ties, and duplicate
solutions. [`RelayBiasSpec`](../../../src/test/scala/chipsldpc/RelayBiasSpec.scala#L41)
checks reduced products and bias saturation;
[`RelayCoefficientsSpec`](../../../src/test/scala/chipsldpc/RelayCoefficientsSpec.scala#L27)
checks coefficient seeds, advancement, stability, and frame reseeding.

The original Relay method is described by
[Müller et al., *Improved belief propagation is sufficient for real-time decoding
of quantum memory*](https://arxiv.org/abs/2506.01779). The linked production
symbols above define this implementation's arithmetic and controller. The
experiment workflow is described in
[Relay experiment workflow](../experiments/relay-bp.md).
