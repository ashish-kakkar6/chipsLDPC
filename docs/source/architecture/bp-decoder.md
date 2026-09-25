# BP decoder

[`StaticTannerDatapath.scala`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala)
contains the shared fixed-graph min-sum network. [`BpDecoder.scala`](../../../src/main/scala/chipsldpc/BpDecoder.scala)
adds an autonomous early-terminating controller.

## Static Tanner network

`TannerGraph.fromRows(variableCount, rowOnes)` is the canonical graph input.
`TannerNodeGraphs.from` derives local CNU and VNU ports from its stable,
row-major edge identifiers.

`StaticTannerCore` instantiates:

- one `StaticCheckStage` for each parity check;
- one `StaticVariableStage` for each variable;
- one fixed connection for every graph edge; and
- one combinational `ConvergenceChecker` for
  $H\hat e + s$ over $\mathrm{GF}(2)$.

An accepted `load` stores the syndrome and unsigned prior magnitudes. Every
variable-to-check message starts as the positive prior of that variable.

An accepted `step` starts one iteration. All check stages update on the first
clock and all variable stages commit on the second. The immediate `commit`
view is used by autonomous controllers; `StaticTannerDatapath.result` exposes
the registered view. There is no row-by-row runtime schedule.

## Node arithmetic

`CheckNode` computes syndrome-adjusted exclusive signs and a
duplicate-preserving first/second minimum pair. An edge uses the second minimum
when its input magnitude equals the first. Available scaling policies are:

- `NoScale`: preserve the magnitude;
- `VallsScale(a, b)`: `(x >> a) + (x >> b)`, clipped to the magnitude width;
- `RampScale(maxShift)`: `x - (x >> t)` for controls through `maxShift`, then
  `x`.

`VariableNode` converts incoming sign-magnitude messages to signed values,
adds them to its bias, and computes one extrinsic value per edge. The hard
decision is one only when the unsaturated total is negative. Stored marginals
are signed and saturated; outgoing magnitudes are saturated separately.

## Autonomous vanilla BP

`VanillaBpConfig` fixes the graph, maximum iterations, quantization, and check
scaling. Its defaults use four magnitude bits, seven signed accumulator bits,
and the ramp policy.

`VanillaBpDecoder` accepts `StaticDecoderInput` through `io.in`. It runs until
the residual is zero or the frame limit is reached, then holds a
`BpDecoderResult` on `io.out` until accepted. The result contains:

- success and correction bits;
- final signed marginals and residual;
- completed iterations; and
- `legsExecuted = 1` and `solutionsFound` equal to the success flag.

When `runtimeIterationLimit` is elaborated, the optional limit port may select
any positive prefix of the configured capacity. Each completed iteration costs
exactly two decoder clocks. Output backpressure extends interface latency but
does not alter the reported iteration count.

## Inspect and test

```sh
./scripts/emit.sh static-steane
./scripts/emit.sh vanilla-steane
./mill chipsLDPC.test.testOnly chipsldpc.StaticTannerDatapathSpec
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
```

The maintained large experiment is in `examples/BivariateBicycle144BpOnly/`.
Relay control is described in [Relay BP](relay-bp.md).
