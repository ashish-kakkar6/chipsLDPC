# BB144 vanilla BP

```sh
./chipsldpc run experiments/bb144-vanilla.toml --out runs/bb144-vanilla
```

This profile uses four message-magnitude bits plus a sign, seven signed marginal
bits, and at most 30 min-sum iterations. Each shot stops at syndrome consistency
or the cap. Nonconvergence counts as failure, including when the returned
correction happens to match the logical observable.

[Setup](../getting-started.md) · [Circuit and units](bb144-model.md) ·
[Archived results](bb144-results.md#vanilla-bp)

[`VanillaBpDecoder`](../../../src/main/scala/chipsldpc/BpDecoder.scala)
implements the stopping rule. The sparse correction streamer emits asserted
fault indices in ascending order. With always-ready outputs, the wrapper's
measured clock count is

```{math}
C=2I+1+N_{\mathrm{occupied\ banks}}+w(\hat e).
```

Here $I$ is executed iterations and $w(\hat e)$ is correction weight. Input-file
parsing and external transport are outside this count. Converting clocks to
seconds requires a measured target clock.

The new runner writes `results/summary.csv`, `results/summary.json`, and
`results/logical_failure.png` (also PDF). The frozen archive retains its original
CSV names and per-cycle plots.
