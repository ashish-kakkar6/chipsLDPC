# Relay BP

[`RelayBpDecoder.scala`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala)
runs Relay-BP-S over the same static Tanner network as vanilla BP. It changes
the VNU bias and controller state; it does not duplicate the graph datapath.

## Bias and coefficients

For prior $\Lambda$, previous marginal $M$, and fixed-point coefficient
$\beta$, `RelayBias` computes

```{math}
B = \beta\Lambda + (1-\beta)M.
```

[`RelayBias.scala`](../../../src/main/scala/chipsldpc/RelayBias.scala) truncates
each magnitude partial product before addition, restores its sign, and
saturates the mixed result to the accumulator width. The default paper profile
uses four magnitude bits, five signed accumulator bits, and a four-bit
coefficient with three fractional bits.

`LfsrRelayCoefficients` contains one deterministic 16-bit Galois LFSR per
variable. A frame starts with coefficient 7. Each later leg advances every
LFSR once and maps its low bits to coefficients 3 through 10. Coefficients stay
constant within a leg, and each accepted frame restores the same initial
state.

## Leg control

Leg zero runs for at most `initialIterations`; later legs run for at most
`relayIterations`. A leg ends early on a zero residual. At a leg boundary:

- signed marginals remain available as memory;
- edge messages restart from immutable positive priors;
- the local scaling schedule restarts; and
- coefficient generators advance for the next leg.

These changes occur on the terminal VNU commit and add no controller clock.
`RelayBpConfig.maximumLegs` counts all hardware legs, including leg zero. The
BB144 experiment accepts a count of randomized legs and maps it to this total.

Relay stops after `solutionTarget` syndrome-consistent candidates or the frame
leg limit. Candidate score is the sum of immutable prior magnitudes at asserted
correction positions. The lowest score wins; an equal score keeps the earlier
candidate.

`io.legTrace` emits a nonblocking event at each terminal leg commit. It reports
the zero-based leg index, local iterations, and convergence flag. A completed
frame takes exactly twice its total BP iterations in decoder clocks; leg
transitions add none.

## Result semantics

`io.out` uses `BpDecoderResult`:

- `correction` is the best consistent candidate, or the final decision if none
  converged;
- `marginal` is always the final leg's soft state;
- `solutionsFound`, `legsExecuted`, and `totalIterations` report completed
  work; and
- failure returns the final leg's coherent correction and residual snapshot.

When `runtimeLegLimit` is elaborated, a frame may select a positive prefix of
the configured leg capacity.

## Inspect and test

```sh
./scripts/emit.sh relay-steane
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayBiasSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayCoefficientsSpec
```

The full experiment contract is in `examples/BivariateBicycle144RelayBp/`.
