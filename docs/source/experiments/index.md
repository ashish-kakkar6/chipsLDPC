# Model and result reference

```{toctree}
:maxdepth: 1

BB144 circuit model <bb144-model>
Archived BB144 results <bb144-results>
BP only <bp-only>
Relay BP <relay-bp>
Iteration budget <iteration-budget>
```

Start with [Getting started](../getting-started.md) for a small RTL run, or
[Reproduce the main results](../reproduce-results.md) for the BB144 profiles.
These reference pages define the model, numerical profiles, and archived data.

The shared benchmark code prepares circuit-level samples, emits decoder-specific
artifacts, runs Verilator, and classifies logical outcomes. The legacy BB144
archive uses the original Pauli-frame sampler and metadata. Its provenance is
separate from new runs made through the experiment runner.
