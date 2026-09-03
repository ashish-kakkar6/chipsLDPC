# Fixed 30-iteration rotated-surface example

This example specializes the production static decoder for Stim rotated-memory-X
circuits at distances 3, 5, and 7. It emits SystemVerilog only, simulates exactly
30 iterations with Verilator, and checks every RTL iteration against the pure
Scala model.

Create the repository-local Python environment once and run:

```sh
./scripts/setup-stim.sh
./examples/RotatedSurfaceCode30/run.sh
```

For each distance, `build/generated/rotated-surface-30/dN/rtl/` contains only
`StaticTannerArtifact.sv`. `result.json` contains exactly:

- `soft_outputs`: signed quantized final marginal LLRs;
- `corrections`: final hard-decision bits;
- `converged`: whether the correction clears the sampled syndrome;
- `logical_failure`: true if decoding did not converge or changed the sampled
  logical observable.

Stim inputs and provenance are under `stim/`; Scala golden records and Verilator
build products are under `verification/`. These are verification data, not
reported decoder results. Larger distances produce large unrolled artifacts, so
the d=7 host compilation can take several minutes.
