# BB144 iteration-budget sweep

```sh
./chipsldpc run experiments/bb144-p003.toml --out runs/bb144-p003
```

This is the [main result profile](../reproduce-results.md): $p=0.003$,
20,000 shared shots, $T_0=T_r=60$, $S=5$, and total caps
`60 120 180 300 540 1020 2040 4080`. All points reuse the saved corpus and one
maximum-capacity Verilator artifact. The stopping budget is a runtime input.

For Relay, every cap must be a whole-leg budget:

```{math}
B=T_0+RT_r,\qquad R\in\mathbb Z_{\ge0},\qquad L=R+1.
```

The runtime input is the total leg count $L$. Vanilla uses its iteration cap
directly. The [controller reference](../architecture/index.md) describes the
fixed graph and runtime inputs.

For executed counts $I_1,\ldots,I_N$ and $F$ failures, the plotted coordinates are

```{math}
x=\bar I=\frac1N\sum_k I_k,\qquad y=P_{\mathrm{word}}=\frac FN.
```

Vertical intervals use Wilson 95% limits. The archived figure also includes a
mean-iteration interval $1.96s_I/\sqrt N$, with sample standard deviation $s_I$.
The new summary plot shows mean iterations without a horizontal interval. The x-axis measures
executed work; the y-axis is failure per whole shot without a per-cycle transform.

At a true failure probability of $10^{-4}$, 10,000 shots give only one expected
failure. Use the interval and observed failure count when assessing a change.
[Saved settings and provenance](bb144-results.md#relay-iteration-budget-sweep)
distinguish the archived curve from a new simulation.
