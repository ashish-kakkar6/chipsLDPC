# chipsLDPC

`chipsLDPC` is a small Chisel/CIRCT research generator for fixed-graph qLDPC
decoder hardware. It implements reusable min-sum nodes and
an independent binary Gauss–Jordan mesh.

## Current milestone

- Balanced, duplicate-preserving two-minimum finder.
- CNU exclusive sign, minimum selector, and either static Valls scaling or an
  iteration-controlled shift ramp.
- VNU signed marginal, hard decision, extrinsic subtraction, and saturation.
- Deterministic Relay memory bias with registered marginal feedback.
- A pure Scala Tanner graph with validated adjacency and stable row-major edge
  numbering; it introduces no runtime hardware.
- Rooted check and variable views that map future CNU/VNU ports onto those
  global edges.
- A graph-generated static datapath with one registered CNU cycle and one
  registered VNU cycle, checked against an independent Scala integer model.
- A file-driven example that specializes the graph from sparse `H`, emits RTL,
  and checks every fixed iteration of that exact artifact in Verilator.
- A Stim-derived rotated-surface-code example for distances 3, 5, and 7 that
  archives DEM priors and logical-observable rows separately from RTL.
- A fixed 30-iteration surface-code profile that emits SystemVerilog only and
  reports only soft outputs, corrections, convergence, and logical failure.
- A pinned `[144,12,12]` bivariate-bicycle Z-check-sector experiment with one
  all-column ranking and a 64-to-128-to-256 OSD-0 fallback ladder.
- A [parameterized binary Gauss–Jordan mesh](src/main/scala/chipsldpc/GaussJordan/README.md)
  assembled from reusable column and diagonal processing elements.
- An autonomous BP/OSD-0 composition with optional filtering and scope, one
  ranked frame, compile-time solver prefixes, and explicit cycle accounting.

The parity-check matrix is Scala elaboration data. Its canonical source is
`TannerGraph.fromRows(variableCount, rowOnes)`; column adjacency and edge-port
mappings are derived rather than independently specified. Syndrome and messages
are runtime hardware data.

The canonical node-view example is one CSS sector of the
[Steane `[[7,1,3]]` code](https://errorcorrectionzoo.org/c/steane):
`rowOnes = [[3,4,5,6], [1,2,5,6], [0,2,4,6]]`. Since its Hamming-code
blocks satisfy `H_X = H_Z`, the same Tanner topology applies to either sector.

## Locked semantics

- Edge messages use separate sign and unsigned magnitude fields.
- A complete sign--magnitude zero has sign zero; CNU parity metadata is
  canonicalized after the VNU selects its magnitude.
- Duplicate minima are retained: `(2, 2, 5) -> (2, 2)`.
- An edge selects the second minimum when its incoming magnitude equals the
  first minimum.
- A correction bit is one exactly when its signed marginal is negative; zero
  maps to no correction.
- Arithmetic widths and saturation points are explicit.
- The Relay default is `Quantization(4, 7)` with `RampScale(4)`; its input and
  memory scales remain the separate constants `S = 2` and `M = 8`.

## Use

Requirements are Java 17 or newer and Verilator. Mill is the only supported
build interface and is included in the repository. The optional Stim examples
use the repository-local Python environment created by `scripts/setup-stim.sh`.

```sh
./scripts/test.sh
./scripts/emit.sh static-steane
./scripts/verify-rtl.sh build/generated/static-steane/StaticTannerDatapath.sv StaticTannerDatapath
./examples/StaticTannerDatapath/run.sh
./examples/EndToEnd/run.sh
./scripts/setup-stim.sh
./examples/RotatedSurfaceCode/run.sh 3
./examples/RotatedSurfaceCode30/run.sh
./scripts/setup-bb144.sh
./examples/BivariateBicycle144/run.sh
./examples/BpFilteredOsd0/run.sh
```

The emission step writes inspectable FIRRTL-dialect MLIR and synthesizable
SystemVerilog under `build/generated/<top>/`. Available example tops are:

```text
two-min  check-valls  check-relay  variable  relay-variable  relay-unit  iteration  convergence  static-steane  bp-filtered-osd0-steane  pe-col  pe-diag  trapezoid-mesh
```

Focused tests can be run directly, for example:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.CheckNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.VariableNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.ConvergenceCheckerSpec
./mill chipsLDPC.test.testOnly chipsldpc.StaticTannerDatapathSpec
./mill chipsLDPC.test.testOnly chipsldpc.EndToEndSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerGraphSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerNodeGraphsSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./mill chipsLDPC.test.testOnly chipsldpc.osd.BpFilteredOsd0Spec
```

The Gauss–Jordan [PE](examples/GaussJordan/README.md) and
[mesh](examples/GaussJordan/TrapezoidMesh/README.md) examples run focused tests
and leave both MLIR and SystemVerilog artifacts ready for inspection.
The [file-driven decoder example](examples/EndToEnd/README.md) records its
validated input, golden trajectory, exact emitted RTL, and verified result.
The [rotated-surface example](examples/RotatedSurfaceCode/README.md) derives
that input and its logical-observable matrix from a Stim detector error model.
The [fixed 30-iteration profile](examples/RotatedSurfaceCode30/README.md) emits
only SystemVerilog and narrows each final result to four decoder outcomes.
The [bivariate-bicycle experiment](examples/BivariateBicycle144/README.md)
reconstructs the pinned Z-check circuit, emits the progressive BP/OSD artifact,
and records 1000 shots at `p=0.005` by default.
The [BP-filtered-OSD0 example](examples/BpFilteredOsd0/README.md) verifies the
exact emitted hierarchy against independent BP and GF(2) software models.

## Layout

```text
src/main/scala/chipsldpc/  pure elaboration data, generator, and hardware
src/test/scala/chipsldpc/  independent model and Verilator-backed tests
examples/                  focused, inspectable generation flows
scripts/                   build, emit, and emitted-RTL checks
paper/main.tex             evolving research manuscript
```

Generated artifacts and experiment results should remain separate from source.
An emitted artifact intended for a result should be archived with its generator
configuration, Git revision, and tool versions.
