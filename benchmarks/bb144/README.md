# BB144 benchmark support

This directory is shared infrastructure, not a third decoder example. It keeps
the physical experiment fixed while
[`examples/BivariateBicycle144BpOnly`](../../examples/BivariateBicycle144BpOnly/README.md)
and
[`examples/BivariateBicycle144RelayBp`](../../examples/BivariateBicycle144RelayBp/README.md)
select different BP implementations.

- `bb144.py` constructs the pinned Z-check circuit, DEM, priors, deterministic
  shots, logical-observable rows, and small verification fixtures.
- `sim_main.cpp` drives a generated Verilator artifact and writes one raw CSV
  row per shot.
- `report.py` validates and aggregates raw rows, then writes timing and logical
  failure tables and plots, plus Relay per-leg clock tables and a plot when a
  trace is present. The emitted decoder configuration is embedded in
  `results.json` for provenance.
- `requirements.txt` pins the Python-side circuit dependencies.

Keep decoder selection and hardware emission in the two example directories.
Changes to physical sampling, logical definitions, or reporting belong here so
both decoders continue to receive the same benchmark contract.
