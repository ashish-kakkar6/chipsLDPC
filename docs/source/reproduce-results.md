# Reproduce the main results

The main figure measures Relay-BP word failure probability at $p=0.003$ against
mean executed iterations on the `[[144,12,12]]` bivariate-bicycle Z-check sector.
Each point uses the same 20,000 physical circuit shots.

## Check the archived figure

```sh
./chipsldpc results check
```

This checks the 22 saved records underlying the three archived figures, their
profiles, confidence intervals, and file hashes. It needs Python only. To redraw
them after `./chipsldpc setup`:

```sh
./chipsldpc results plot --out runs/archived-figures
```

The saved [budget CSV](_static/bb144-results/legacy-v1/budget.csv) reports
667 failures in 20,000 shots at a 60-iteration cap and 18 in 20,000 at a
4,080-iteration cap. The latter estimate is $9.0\times10^{-4}$, with a Wilson
95% interval of approximately $[5.69\times10^{-4},1.42\times10^{-3}]$.

## Run the same profile

After [setup](getting-started.md), run:

```sh
./chipsldpc run experiments/bb144-p003.toml --out runs/bb144-p003
```

| Setting | Value |
| --- | --- |
| Physical error probability | 0.003 |
| Noisy rounds / closure rounds | 12 / 2 |
| Sector | Z-check detectors, X-error component |
| Shots shared across budgets | 20,000 |
| Initial and later leg caps | 60 iterations each |
| Candidate target | 5 |
| Total iteration budgets | 60, 120, 180, 300, 540, 1020, 2040, 4080 |
| Additional Relay legs | 0, 1, 2, 4, 8, 16, 33, 67 |
| Sampling seed | 14412 |

This is a substantial simulation. The historical run took approximately
4.1 hours on 16 workers, excluding hardware generation and compilation. That
measurement is not a runtime guarantee. Start with `experiments/smoke.toml` to
check your installation.

The current run creates a **new dataset with the same scientific profile**.
The archive does not include its original full sample corpus, executable, or
recoverable producer revision, so a matching parameter file cannot guarantee
identical failures. Preserve the new run directory for subsequent comparisons.
See [archive provenance](experiments/bb144-results.md#data-provenance-and-verification-scope).

## Other profiles

```sh
./chipsldpc run experiments/bb144-vanilla.toml --out runs/bb144-vanilla
./chipsldpc run experiments/bb144-relay.toml --out runs/bb144-relay
```

These probability sweeps cover $p=.001,.002,\ldots,.007$. Their complete decoder
profiles differ in arithmetic width, stopping target, and iteration budget.
The [saved profiles](experiments/bb144-results.md#saved-profiles) state those
settings. They do not isolate the causal effect of Relay alone.

## Interpret the plot

A word is a complete 12-round memory shot across 12 logical observables in one
sector. A failure includes nonconvergence or any logical mismatch. This is not
a joint XZ failure rate. The budget figure uses the raw fraction $F/N$ and
Wilson 95% intervals. Mean executed iterations measure work, not the configured
cap or a synthesized clock frequency.

Probability-sweep reference plots additionally show
$q=1-(1-F/N)^{1/12}$, an equivalent per-cycle rate. It is a normalization of
whole-shot failure. See the [model and units](experiments/bb144-model.md).
