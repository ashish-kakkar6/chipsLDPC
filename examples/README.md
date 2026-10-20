# Examples

Runnable examples are intentionally limited to the two BB144 decoder variants:

- [`BivariateBicycle144BpOnly`](BivariateBicycle144BpOnly/README.md) is the
  complete vanilla-BP RTL and Verilator sweep.
- [`BivariateBicycle144RelayBp`](BivariateBicycle144RelayBp/README.md) is the
  Figure 7 Relay-5 parameter profile, including per-leg clock traces.

[`BivariateBicycle144IterationBudgetSweep`](BivariateBicycle144IterationBudgetSweep/README.md)
is a meta-example over either variant. It reuses one sample corpus and one RTL
artifact to produce a Figure-4-style iteration-budget curve.

Run the documented commands from the repository root after the
[toolchain setup](../docs/source/getting-started.md) and
[`scripts/setup-bb144.sh`](../scripts/setup-bb144.sh) for Python dependencies.
The run scripts clear their selected generated output directories; the guides
use fresh directory names to keep archived results separate.

The [circuit-model guide](../docs/source/experiments/bb144-model.md) defines the
12 noisy plus two noiseless closure rounds and single-sector failure event.
The [archived results](../docs/source/experiments/bb144-results.md) provide exact
saved settings and CSVs. Parameter correspondence with a paper is not a claim
to reproduce its full XZ dataset or synthesized hardware timing.

Leaf arithmetic, Tanner-graph structure, message passing, convergence,
streaming, sorting, and GF(2) solver behavior belong in `src/test`. Inspectable
RTL for a leaf can be emitted with [`scripts/emit.sh`](../scripts/emit.sh);
duplicating a test as an
example is deliberately avoided.
