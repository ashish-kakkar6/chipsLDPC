# Gauss–Jordan PE example

These leaf modules are small toy tops: their complete behavior is exhaustively
tested, and their CIRCT output is short enough to inspect directly.

From the repository root, run the complete example with:

```sh
./examples/GaussJordan/run.sh
```

The same stages remain independently runnable:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec

./scripts/emit.sh pe-col build/generated/gauss-jordan/pe-col
./scripts/emit.sh pe-diag build/generated/gauss-jordan/pe-diag

./scripts/verify-rtl.sh build/generated/gauss-jordan/pe-col/pe_col.sv pe_col
./scripts/verify-rtl.sh build/generated/gauss-jordan/pe-diag/pe_diag.sv pe_diag
```

Inspect the generated artifacts at:

```text
build/generated/gauss-jordan/pe-col/pe_col.fir.mlir
build/generated/gauss-jordan/pe-col/pe_col.sv
build/generated/gauss-jordan/pe-diag/pe_diag.fir.mlir
build/generated/gauss-jordan/pe-diag/pe_diag.sv
```

The `.fir.mlir` files show FIRRTL-dialect MLIR before CIRCT lowering. The `.sv`
files are synthesizable artifacts that Verilator or a future FPGA flow can
consume independently. Generated files remain outside version control.
