# Examples

Runnable examples are intentionally limited to the two BB144 decoder variants:

- [`BivariateBicycle144BpOnly`](BivariateBicycle144BpOnly/README.md) is the
  complete vanilla-BP RTL and Verilator sweep.
- [`BivariateBicycle144RelayBp`](BivariateBicycle144RelayBp/README.md) is the
  Figure 7 Relay-5 parameter profile, including per-leg clock traces.

[`BivariateBicycle144IterationBudgetSweep`](BivariateBicycle144IterationBudgetSweep/README.md)
is a meta-example over either variant. It reuses one sample corpus and one RTL
artifact to produce a Figure-4-style iteration-budget curve.

Leaf arithmetic, Tanner-graph structure, message passing, convergence,
streaming, sorting, and GF(2) solver behavior belong in `src/test`. Inspectable
RTL for a leaf can be emitted with `scripts/emit.sh`; duplicating a test as an
example is deliberately avoided.
