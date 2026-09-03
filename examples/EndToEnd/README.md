# File-driven end-to-end example

This example reads one sparse parity-check matrix, quantized prior vector,
syndrome, and fixed iteration count. Pure Scala computes every expected
iteration, CIRCT emits a graph-specialized RTL artifact, and standalone
Verilator compares that exact `.sv` file before writing the final result.

```sh
./examples/EndToEnd/run.sh [problem.json] [output-directory]
```

The defaults are `examples/EndToEnd/problem.json` and
`build/generated/end-to-end/`. `row_ones` is the zero-based sparse form of
H; the row count and all column adjacency are derived. Priors are unsigned
four-bit quantized LLR magnitudes. Quantization and scaling remain the locked
`Quantization(4,7)` and `RampScale(4)` repository defaults.

The output directory contains the copied problem, FIRRTL-dialect MLIR, exact
SystemVerilog, integer golden records, Verilator build, and `result.json`.
Every intermediate marginal, correction, residual, convergence bit, handshake,
and two-cycle iteration is checked. Non-convergence is a valid fixed-iteration
result; only disagreement is a verification failure.

`marginal` is the verified quantized min-sum soft metric. The reported
`approx_error_probability = 1 / (1 + exp(marginal / 2))` is an uncalibrated
presentation value, not an exact posterior probability and not part of the
bit-exact acceptance condition.
