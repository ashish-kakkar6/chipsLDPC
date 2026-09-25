# Architecture

```{toctree}
:maxdepth: 1
:hidden:

BP decoder <bp-decoder>
Relay BP <relay-bp>
Filtered OSD-0 <filtered-osd>
Systolic GF(2) solver <systolic-gf2>
```

The generator specializes hardware to one Tanner graph at elaboration time.
The parity-check matrix, edge numbering, node degrees, arithmetic widths, and
iteration capacity are therefore constants in emitted RTL. Runtime inputs
contain a syndrome, quantized priors, and optional decoder limits.

## Structure

| Layer | Current source | Role |
| --- | --- | --- |
| Graph | [`graph/TannerGraph.scala`](../../../src/main/scala/chipsldpc/graph/TannerGraph.scala), [`graph/TannerNodeGraphs.scala`](../../../src/main/scala/chipsldpc/graph/TannerNodeGraphs.scala) | Validate sparse rows and derive stable edge and node-port maps. |
| Arithmetic | [`TwoMin.scala`](../../../src/main/scala/chipsldpc/TwoMin.scala), [`CheckNode.scala`](../../../src/main/scala/chipsldpc/CheckNode.scala), [`VariableNode.scala`](../../../src/main/scala/chipsldpc/VariableNode.scala) | Implement fixed-point min-sum updates. |
| Static network | [`StaticTannerDatapath.scala`](../../../src/main/scala/chipsldpc/StaticTannerDatapath.scala) | Instantiate one CNU per check, one VNU per variable, and fixed edge wiring. |
| Controllers | [`BpDecoder.scala`](../../../src/main/scala/chipsldpc/BpDecoder.scala), [`RelayBpDecoder.scala`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala) | Run autonomous vanilla or Relay BP. |
| Post-processing | `sort/`, `osd/` | Filter soft values and run progressive OSD-0. |
| Linear algebra | `GaussJordan/` | Provide the binary systolic mesh and framed solver. |

The BP network is fully spatial for its elaborated graph. One flooding
iteration takes one registered check-node clock followed by one registered
variable-node clock. The decoder accepts one frame at a time; it does not bank
state or overlap frames.

## Interfaces

Top-level controllers use Chisel `Decoupled` input and output channels. A
producer holds `valid` and payload stable until `ready`; a consumer may apply
backpressure to result and correction streams. Internal configuration case
classes are elaboration data and do not create runtime configuration ports.

The implementation emits synthesizable SystemVerilog, but this repository does
not claim synthesis frequency, area, power, placement, or board execution.
Algorithm notation is summarized in [QEC background](../qec-background.md).
