# Experiments

```{toctree}
:maxdepth: 1
:hidden:

BP only <bp-only>
Relay BP <relay-bp>
Iteration budget <iteration-budget>
```

The experiment flows use the pinned `[[144,12,12]]` BB144 Z-check problem.
BP-only and Relay-BP share circuit preparation, deterministic shots, Verilator
transport, and reporting.

Install their Python dependencies once:

```sh
./scripts/setup-bb144.sh
```

Generated RTL, raw samples, and reports are written below `build/generated/`.
Keep the saved configuration, source description, Git revision, and tool
versions with any published result.
