# chipsLDPC

`chipsLDPC` is a small Chisel/CIRCT research generator for fixed-graph qLDPC
decoder hardware. The current milestone implements reusable min-sum nodes and
an independent binary Gauss–Jordan mesh; it does not yet implement a complete
decoder controller.

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
- A [parameterized binary Gauss–Jordan mesh](src/main/scala/chipsldpc/GaussJordan/README.md)
  assembled from reusable column and diagonal processing elements.

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
- The Relay default is `Quantization(4, 5)` with `RampScale(4)`; its input and
  memory scales remain the separate constants `S = 2` and `M = 8`.

## Use

Requirements are Java 17 or newer and Verilator. Mill is the only supported
build interface and is included in the repository.

```sh
./scripts/test.sh
./scripts/emit.sh static-steane
./scripts/verify-rtl.sh build/generated/static-steane/StaticTannerDatapath.sv StaticTannerDatapath
./examples/StaticTannerDatapath/run.sh
```

The emission step writes inspectable FIRRTL-dialect MLIR and synthesizable
SystemVerilog under `build/generated/<top>/`. Available example tops are:

```text
two-min  check-valls  check-relay  variable  relay-variable  relay-unit  iteration  convergence  static-steane  pe-col  pe-diag  trapezoid-mesh
```

Focused tests can be run directly, for example:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.CheckNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.VariableNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.ConvergenceCheckerSpec
./mill chipsLDPC.test.testOnly chipsldpc.StaticTannerDatapathSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerGraphSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerNodeGraphsSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
```

The Gauss–Jordan [PE](examples/GaussJordan/README.md) and
[mesh](examples/GaussJordan/TrapezoidMesh/README.md) examples run focused tests
and leave both MLIR and SystemVerilog artifacts ready for inspection.

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
