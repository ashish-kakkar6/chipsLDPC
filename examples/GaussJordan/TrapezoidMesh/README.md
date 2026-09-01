# Trapezoidal mesh example

This inspectable toy elaborates a three-row mesh with two lifted columns and a
two-enabled-cycle reduction delay between adjacent diagonal cells.

From the repository root, run its behavioral test, emit FIRRTL-dialect MLIR and
SystemVerilog, and lint the emitted RTL with Verilator:

```sh
./examples/GaussJordan/TrapezoidMesh/run.sh
```

The stages are independently runnable:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./scripts/emit.sh trapezoid-mesh build/generated/gauss-jordan/trapezoid-mesh
./scripts/verify-rtl.sh \
  build/generated/gauss-jordan/trapezoid-mesh/trapeziod_mesh.sv \
  trapeziod_mesh
```

Inspect the generated artifacts at:

```text
build/generated/gauss-jordan/trapezoid-mesh/trapeziod_mesh.fir.mlir
build/generated/gauss-jordan/trapezoid-mesh/trapeziod_mesh.sv
```

The configuration is Scala elaboration data; input bits, enable, and reduction
control remain runtime hardware signals. Generated files stay outside version
control.
