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

BB144 runs verify prepared fixtures against independent Scala golden models
before each sweep.

Archive published results with the emitted configuration, Git revision, tool
versions, raw rows, and generated reports.
