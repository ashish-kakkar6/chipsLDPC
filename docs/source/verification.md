# Verification

Run the complete Scala reference and Verilator-backed test suite:

```sh
./scripts/test.sh
```

Emit and lint an inspectable hardware target:

```sh
./scripts/emit.sh static-steane
./scripts/verify-rtl.sh \
  build/generated/static-steane/StaticTannerDatapath.sv \
  StaticTannerDatapath
```

The experiment runner compares prepared frames with the independent Scala
integer reference at every requested stopping budget before the bulk RTL run.
`sampling.verification_shots` sets the fixture count (default 8 per probability).
Distinct sampled frames are used first; synthetic single-fault fixtures fill
remaining slots and never enter the failure statistics. This is separate from
an all-shot software comparison. The bulk report recomputes failure from saved
decoder status and logical outcomes and checks shot coverage.

Each run retains resolved configuration, source and artifact hashes, tool
versions, raw rows, and reports. Preserve the whole run directory for a published
result. The historical BB144 archive and the animation snapshot retain their own
verification scope and source identity.

## Implementation checks

The [background](qec-background.md), [BP architecture](architecture/bp-decoder.md),
and [Relay architecture](architecture/relay-bp.md) link equations to production
functions and signals. The suites below check those implementations against
reference calculations and protocol expectations.

The [archived BB144 plots](experiments/bb144-results.md) have a separate
provenance statement. Their summary/data checks do not establish all-shot RTL
equivalence. Check the documentation's saved figures and manifests with:

```sh
make -C docs check-assets
```

| Material | Source or check |
| --- | --- |
| Animation's captured numerical steps and final outcomes | [AnimationTraceSpec.scala](../../src/test/scala/chipsldpc/AnimationTraceSpec.scala); integer reference replay, not waveform timing |
| Shared core and two-clock updates | [StaticTannerDatapathSpec](../../src/test/scala/chipsldpc/StaticTannerDatapathSpec.scala#L8) |
| Autonomous controllers, leg transitions, output selection | [BpDecodersSpec](../../src/test/scala/chipsldpc/BpDecodersSpec.scala#L52) |
| Shared two minima and selector | [TwoMinSpec.scala](../../src/test/scala/chipsldpc/TwoMinSpec.scala), [CheckNodeSpec.scala](../../src/test/scala/chipsldpc/CheckNodeSpec.scala) |
| Signed sums and outgoing messages | [VariableNodeSpec.scala](../../src/test/scala/chipsldpc/VariableNodeSpec.scala) |
| Reduced-product arithmetic | [RelayBiasSpec.scala](../../src/test/scala/chipsldpc/RelayBiasSpec.scala) |
| Deterministic coefficients and frame reset | [RelayCoefficientsSpec](../../src/test/scala/chipsldpc/RelayCoefficientsSpec.scala#L7) |
| Syndrome consistency | [ConvergenceCheckerSpec](../../src/test/scala/chipsldpc/ConvergenceCheckerSpec.scala) |
| Filtered OSD and solver | [FilteredOsd0Spec](../../src/test/scala/chipsldpc/osd/FilteredOsd0Spec.scala), [SystolicGf2SolverSpec](../../src/test/scala/chipsldpc/GaussJordan/SystolicGf2SolverSpec.scala) |
| Figure regeneration and review | {download}`Contributor instructions <../README.md>` |
