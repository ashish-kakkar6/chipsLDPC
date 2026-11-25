# BB144 Relay-BP

```sh
./chipsldpc run experiments/bb144-relay.toml --out runs/bb144-relay
```

This profile uses $T_0=80$, $T_r=60$, $R=600$, and $S=5$. Here $R$ counts
randomized legs after the initial leg, so at most 601 legs execute. The maximum
work is $80+600\times60=36{,}080$ iterations. Arithmetic uses four message-magnitude
bits, five signed marginal bits, and the recorded integer Relay bias profile.

[Setup](../getting-started.md) · [Circuit and units](bb144-model.md) ·
[Archived results](bb144-results.md#relay-bp) ·
[Relay equations](../architecture/relay-bp.md)

A leg stops at syndrome consistency or its iteration cap. The decoder stops at
five converged candidates or the leg limit and returns the converged candidate
with minimum immutable-prior score. Equal scores retain the earlier candidate.
Repeated candidates count toward the target. If no leg converges, it returns
the final decision and reports nonconvergence.

[`RelayBpDecoder`](../../../src/main/scala/chipsldpc/RelayBpDecoder.scala)
implements this rule. Its selected correction and final marginal can describe
different legs. Each iteration takes two core clocks. Leg transitions preserve
stored marginals and reset messages without an extra controller clock.
These cycle counts are not synthesized hardware timing.

The new runner writes `results/summary.csv`, `results/summary.json`, and
`results/logical_failure.png` (also PDF). The model covers one Z-check sector,
not a full XZ reproduction of the FPGA paper's dataset.
