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

BB144 runs verify prepared fixtures against the Scala golden models before
each sweep. The [experiment workflows](experiments/index.md) link the wrapper,
producer, and reporting code for each profile.

Archive published results with the emitted configuration, Git revision, tool
versions, raw rows, and generated reports.

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
| Shared core and two-clock updates | [StaticTannerDatapathSpec](../../src/test/scala/chipsldpc/StaticTannerDatapathSpec.scala#L8) |
| Autonomous controllers, leg transitions, output selection | [BpDecodersSpec](../../src/test/scala/chipsldpc/BpDecodersSpec.scala#L52) |
| Shared two minima and selector | [TwoMinSpec.scala](../../src/test/scala/chipsldpc/TwoMinSpec.scala), [CheckNodeSpec.scala](../../src/test/scala/chipsldpc/CheckNodeSpec.scala) |
| Signed sums and outgoing messages | [VariableNodeSpec.scala](../../src/test/scala/chipsldpc/VariableNodeSpec.scala) |
| Reduced-product arithmetic | [RelayBiasSpec.scala](../../src/test/scala/chipsldpc/RelayBiasSpec.scala) |
| Deterministic coefficients and frame reset | [RelayCoefficientsSpec](../../src/test/scala/chipsldpc/RelayCoefficientsSpec.scala#L7) |
| Syndrome consistency | [ConvergenceCheckerSpec](../../src/test/scala/chipsldpc/ConvergenceCheckerSpec.scala) |
| Filtered OSD and solver | [FilteredOsd0Spec](../../src/test/scala/chipsldpc/osd/FilteredOsd0Spec.scala), [SystolicGf2SolverSpec](../../src/test/scala/chipsldpc/GaussJordan/SystolicGf2SolverSpec.scala) |
| Figure regeneration and review | {download}`Contributor instructions <../README.md>` |
