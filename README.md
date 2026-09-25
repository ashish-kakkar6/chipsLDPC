# chipsLDPC

[Documentation](https://ashish-kakkar6.github.io/chipsLDPC/)

`chipsLDPC` is a small Chisel/CIRCT research generator for fixed-graph qLDPC
decoder hardware. It implements reusable min-sum nodes and
an independent binary Gauss–Jordan mesh.

## Current milestone

- Balanced, duplicate-preserving two-minimum finder.
- CNU exclusive sign, minimum selector, and either static Valls scaling or an
  iteration-controlled shift ramp.
- VNU signed marginal, hard decision, extrinsic subtraction, and saturation.
- Separate autonomous `VanillaBpDecoder` and `RelayBpDecoder` controllers over
  one statically wired Tanner core.
- FPGA-paper Relay arithmetic with per-partial-product truncation, deterministic
  per-VNU LFSR coefficients, persistent inter-leg marginals, and zero-bubble
  message reinitialization.
- A pure Scala Tanner graph with validated adjacency and stable row-major edge
  numbering; it introduces no runtime hardware.
- Rooted check and variable views that map future CNU/VNU ports onto those
  global edges.
- A graph-generated static datapath with one registered CNU cycle and one
  registered VNU cycle, checked against an independent Scala integer model.
- A pinned `[144,12,12]` bivariate-bicycle Z-check-sector BP-only sweep with
  deterministic shots, exact artifact checks, parallel Verilator simulation,
  and explicit logical-failure and cycle reporting.
- A modular Relay-BP implementation and BB144 Figure 7 parameter sweep that
  reuse the BP-only experiment contract and report per-leg clocks.
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
- Existing vanilla results remain locked to `Quantization(4, 7)`. The named
  FPGA-paper Relay profile uses 4-bit magnitudes, 5-bit signed saturated
  marginals, and 4-bit beta coefficients at memory scale `M = 8`.
- Relay leg zero uses beta 7. Later legs advance one deterministic 16-bit
  Galois LFSR per VNU to coefficients in `[3,10]`; every accepted frame reseeds.
- Following Algorithm 1 and `trmue/relay`, the paper's `R=600` is represented
  as 600 randomized legs after leg zero: at most 601 total legs and
  `80 + 600 * 60 = 36,080` BP iterations.
- The lower-level `RelayBpConfig.maximumLegs` field is the total hardware-leg
  bound; the experiment profile performs the `R + 1` mapping explicitly.
- A leg transition preserves saturated marginals, resets edge messages to the
  immutable priors, and restarts the alpha schedule without a controller clock.

## Use

Requirements are Java 17 or newer and Verilator. Mill is the only supported
build interface and is included in the repository. The BB144 benchmark uses
the repository-local Python environment created by `scripts/setup-bb144.sh`.

```sh
./scripts/test.sh
./scripts/emit.sh static-steane
./scripts/verify-rtl.sh build/generated/static-steane/StaticTannerDatapath.sv StaticTannerDatapath
./scripts/setup-bb144.sh
./examples/BivariateBicycle144BpOnly/run.sh
./examples/BivariateBicycle144RelayBp/run.sh
```

The emission step writes inspectable FIRRTL-dialect MLIR and synthesizable
SystemVerilog under `build/generated/<top>/`. Available inspection tops are:

```text
two-min  check-valls  check-relay  variable  iteration  convergence  static-steane  vanilla-steane  relay-steane  bp-filtered-osd0-steane  pe-col  pe-diag  trapezoid-mesh
```

Focused tests can be run directly, for example:

```sh
./mill chipsLDPC.test.testOnly chipsldpc.CheckNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.VariableNodeSpec
./mill chipsLDPC.test.testOnly chipsldpc.ConvergenceCheckerSpec
./mill chipsLDPC.test.testOnly chipsldpc.StaticTannerDatapathSpec
./mill chipsLDPC.test.testOnly chipsldpc.BpDecodersSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayBiasSpec
./mill chipsLDPC.test.testOnly chipsldpc.RelayCoefficientsSpec
./mill chipsLDPC.test.testOnly chipsldpc.EndToEndSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerGraphSpec
./mill chipsLDPC.test.testOnly chipsldpc.graph.TannerNodeGraphsSpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.GaussJordanPESpec
./mill chipsLDPC.test.testOnly chipsldpc.GaussJordan.TrapezoidMeshSpec
./mill chipsLDPC.test.testOnly chipsldpc.osd.BpFilteredOsd0Spec
```

Runnable examples are deliberately restricted to the BB144 decoder comparison.
The [BP-only flow](examples/BivariateBicycle144BpOnly/README.md) and
[Relay-BP flow](examples/BivariateBicycle144RelayBp/README.md) share the
physical experiment and reporting code in
[`benchmarks/bb144`](benchmarks/bb144/README.md). Small structural checks stay
in `src/test`, while `scripts/emit.sh` remains the direct way to inspect leaf
MLIR and SystemVerilog without duplicating those checks as examples.

## Layout

```text
src/main/scala/chipsldpc/  pure elaboration data, generator, and hardware
src/test/scala/chipsldpc/  independent model and Verilator-backed tests
examples/                  BB144 BP-only and Relay-BP experiment wrappers
scripts/                   build, emit, and emitted-RTL checks
paper/main.tex             evolving research manuscript
```

Generated artifacts and experiment results should remain separate from source.
An emitted artifact intended for a result should be archived with its generator
configuration, Git revision, and tool versions.
