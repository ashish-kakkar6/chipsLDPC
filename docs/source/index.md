# chipsLDPC

```{toctree}
:maxdepth: 2
:hidden:

Getting started <getting-started>
Architecture <architecture/index>
Experiments <experiments/index>
Verification <verification>
QEC background <qec-background>
```

`chipsLDPC` is a Chisel/CIRCT generator for fixed-graph quantum LDPC decoder
hardware.

The repository contains:

- vanilla min-sum BP and Relay-BP decoders;
- static Tanner-graph hardware;
- BP-filtered OSD-0;
- a binary systolic Gauss–Jordan solver;
- Verilator-backed tests and BB144 experiments.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/main/scala/chipsldpc/` | Hardware and elaboration data |
| `src/test/scala/chipsldpc/` | Models, tests, and experiment drivers |
| `examples/` | BB144 experiment entry points |
| `benchmarks/` | Shared benchmark and reporting code |
| `scripts/` | Test, emission, and RTL checks |
