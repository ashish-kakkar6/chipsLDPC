# Getting started

## Requirements

- Java 17 or newer
- Verilator
- Python 3.12 or newer for the BB144 benchmark tools

Mill is included in the repository.

## Test the project

Run the full Scala and Verilator test suite:

```sh
./scripts/test.sh
```

Run one focused suite:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.SystolicGf2SolverSpec
```

## Emit RTL

Emit a small static decoder:

```sh
./scripts/emit.sh static-steane
./scripts/verify-rtl.sh \
  build/generated/static-steane/StaticTannerDatapath.sv \
  StaticTannerDatapath
```

Generated MLIR and SystemVerilog are written under `build/generated/`.

## Run the BB144 examples

Prepare the Python environment once:

```sh
./scripts/setup-bb144.sh
```

Commands, scale, and outputs are listed under [Experiments](experiments/index.md).
