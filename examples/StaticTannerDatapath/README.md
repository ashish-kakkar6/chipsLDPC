# Exact emitted-RTL comparison

This example emits the static Steane SystemVerilog artifact, generates expected
records with the test-only pure Scala model, compiles that exact `.sv` file with
Verilator, and compares every output after every iteration.

```sh
./examples/StaticTannerDatapath/run.sh [prior-sets] [iterations] [seed]
```

Defaults are 32 prior sets, four iterations, and seed zero. Every prior set is
tested against all eight syndromes. Error probabilities are sampled
log-uniformly from `[1e-4, 0.2)` and converted to four-bit integer LLR priors by
`round(2 * log((1-p)/p))` followed by saturation.

All generated files stay under `build/generated/static-tanner-artifact/`. A
mismatch prints the record and signal and exits nonzero; success reports the
number of matching Scala golden records.
