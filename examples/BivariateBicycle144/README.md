# BB144 progressive OSD-0

This is the repository's main bivariate-bicycle example. It pins Bravyi et
al.'s `[[144,12,12]]` circuit, keeps only Z-check detectors, and exactly removes
singleton checks before elaboration. The resulting circuit-noise decoder
problem has `m=936`, `n=8784`, and 12 logical observables.
The circuit parameters are pinned to
[`sbravyi/BivariateBicycleCodes@fa77e33`](https://github.com/sbravyi/BivariateBicycleCodes/tree/fa77e3333d3ec44c79d8f914dd24c040d1da471b).

The generated hardware runs at most 30 min-sum BP iterations. On
non-convergence it ranks every column once by ascending `|soft|`, solves the
first 64 columns, and advances to 128 and then 256 columns only when the
current system is inconsistent:

```text
BP -> one sort -> K=64 -> solved
                  \-> inconsistent -> K=128 -> solved
                                           \-> inconsistent -> K=256 -> solved/failure
```

There is no soft-value filter and no overflow failure: only the first 256
ranked columns are retained. A successful solver streams its indexed
correction; an inconsistent 256-column system returns the explicit
`osd_inconsistent` status.

All three prefixes are structural triangular meshes, so solver area and elaboration
grow quadratically with `K`; smaller prefix arguments are useful workflow smoke
tests, while 64/128/256 is the intended research configuration.

After installing the pinned Python dependencies, run the default 1000 shots at
`p=0.005`:

```sh
./scripts/setup-bb144.sh
./examples/BivariateBicycle144/run.sh
```

The output directory, shot count, and elaboration-time prefixes are optional:

```sh
./examples/BivariateBicycle144/run.sh <output> <shots> <k0> <k1> <k2>
```

The default output is `build/generated/bb144-progressive-osd0/`:

```text
source/                    pinned circuit, DEM, sparse problem, and 1000 shots
artifact/rtl/              immutable graph-specialized SystemVerilog
artifact/config.{json,txt} human- and machine-readable [64,128,256] contract
verification/              independent Scala golden and exact Verilator result
parallel/                  hashed inputs, shard results, and measured throughput
raw/shots.csv              one status, logical result, and timing row per shot
results/                   aggregate failure and cycle reports
```

The first shot is checked bit-for-bit against independent BP and GF(2) Scala
models. The benchmark is then split into 100-shot shards and run by four
independent instances of the same Verilated artifact. Set `SHARD_SIZE` and
`SIM_WORKERS` to tune that simulation-only stage. Reported cycles are
architecture cycles, not post-place-and-route timing.
