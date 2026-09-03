# Rotated-surface-code end-to-end example

This example follows the `systolicLDPC` data boundary. Stim generates a
`surface_code:rotated_memory_x` circuit with `rounds = distance` and circuit
noise probability `0.05`. The decomposed detector error model defines:

- sparse detector matrix `H` in `problem.json`;
- one probability and quantized LLR prior per DEM effect; and
- sparse logical-observable rows in `metadata.json`.

Run the exact Scala-golden versus emitted-SystemVerilog check with:

```sh
./scripts/setup-stim.sh
./examples/RotatedSurfaceCode/run.sh [distance] [output-directory] [iterations]
```

Distance must be 3, 5, or 7; the default is 3. Generated Stim inputs live
under `stim/`, while MLIR, SystemVerilog, golden records, and the Verilator
result live under `rtl/`. `logical_result.json` reports whether a converged
correction reproduces Stim's sampled logical observable. A logical decoding
failure is a measured algorithm outcome, not a Scala/RTL implementation
failure; any hardware/software disagreement still stops the script.

To check all requested graph specializations, run
`for d in 3 5 7; do ./examples/RotatedSurfaceCode/run.sh "$d"; done`.
These are fully unrolled static artifacts, so host elaboration and Verilator
compile time grow substantially with distance even though one decoder
iteration remains the same two-cycle CNU/VNU schedule.

The prior conversion uses the same definition as `systolicLDPC`,
`LLR = log((1-p)/p)`, adapted to this repository's locked unsigned four-bit
prior with scale 2. Raw Stim probabilities and unquantized LLRs remain in the
metadata for provenance.
