# QEC background

For one binary decoding sector, let
$H\in\mathbb{F}_2^{m\times n}$ be a parity-check matrix, $e$ an unknown error,
and $s=He$ the measured syndrome. A decoder returns a correction
$\hat e$ whose syndrome matches the measurement:

```{math}
H\hat e = s.
```

The repository represents $H$ as elaboration-time sparse rows. Its Tanner
graph has one variable node per column, one check node per row, and one edge per
nonzero matrix entry. The BB144 experiments decode one CSS detector sector and
check logical observables separately.

## Min-sum messages

Let $R_{i,j}$ be the variable-to-check message on edge $(i,j)$ and let
$\mathcal N(i)$ be the variables adjacent to check $i$. The check update uses
the syndrome-adjusted exclusive sign and minimum magnitude

```{math}
C_{i,j} =
(-1)^{s_i \oplus
\bigoplus_{j'\in\mathcal N(i)\setminus j}[R_{i,j'}<0]}
\;g_t\!\left(
\min_{j'\in\mathcal N(i)\setminus j}|R_{i,j'}|
\right),
```

where $g_t$ is the configured check-scaling policy. Hardware retains both the
first and second minima so every edge can exclude its own input. Duplicate
minima are preserved.

For variable $j$, bias $B_j$, and adjacent checks $\mathcal M(j)$, the marginal
and outgoing extrinsic messages are

```{math}
M_j = B_j + \sum_{i\in\mathcal M(j)}C_{i,j},
\qquad
R_{i,j} = M_j - C_{i,j}.
```

The hard decision is one exactly when the unsaturated marginal is negative;
zero selects no correction. Signed marginals and sign-magnitude edge messages
use explicit saturation.

Vanilla BP sets $B_j$ to the immutable prior. [Relay BP](architecture/relay-bp.md)
mixes that prior with a previous-leg marginal. Both use the same statically
wired [BP datapath](architecture/bp-decoder.md).

## Post-processing

[Filtered OSD-0](architecture/filtered-osd.md) uses final soft values to choose
a bounded, ordered set of candidate columns. It solves the restricted binary
system with the [systolic GF(2) solver](architecture/systolic-gf2.md), then
streams selected correction bits in original variable coordinates.

These blocks operate on quantized hardware values. Floating-point decoder
equations describe intent; exact behavior is defined by the configured widths,
scaling, truncation, saturation, graph, and stopping limits.
