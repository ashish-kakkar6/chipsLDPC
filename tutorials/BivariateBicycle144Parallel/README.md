# BB144: matrix to parallel RTL experiment

This tutorial reproduces the `[[144,12,12]]` bivariate-bicycle experiment with
10,000 shots at each of seven physical error probabilities. Generation,
elaboration, RTL verification, bulk simulation, and analysis are separate
stages. Only the first three stages require Python scientific packages or
Chisel; bulk execution needs only Python 3, a simulator, immutable inputs, and
the manifest in `benchmarks/rtl_shards`.

```text
code matrices + circuit noise
            |
            v
Stim DEM -> sparse decoder graph -> graph-specialized SystemVerilog
                                      |
                         exact Scala/RTL preflight
                                      |
                 immutable input shards + one simulator
                                      |
                     independent Verilator processes
                                      |
                         raw CSV -> tables + plots
```

## 1. What matrix is being constructed?

Let `P_r` be the cyclic right-shift permutation matrix of size `r`. With
`ell=12` and `m=6`, define the commuting `72 x 72` matrices

```text
x = P_12 ⊗ I_6                    A = x^3 xor y xor y^2
y = I_12 ⊗ P_6                    B = y^3 xor x xor x^2
```

The CSS check matrices are

```text
H_X = [ A   B ]                    H_Z = [ B^T   A^T ]
```

and each has shape `72 x 144`. The generator verifies `H_X H_Z^T = 0` and
checks that the derived logical matrices commute with the opposite checks.
This defines the quantum `[[144,12,12]]` code, but it is not yet the matrix
elaborated into decoder hardware.

The pinned reference circuit performs twelve noisy syndrome cycles. Stim turns
the two CSS sectors into detector error models (DEMs). Each DEM error mechanism
becomes a decoder variable; each detector becomes a parity check; its error
probability becomes a four-bit quantized LLR prior. The combined raw graph has
`m=1944` checks and `n=17640` variables. Exact substitution of 72 singleton
checks produces the static hardware graph:

```text
m = 1872 checks       n = 17568 variables       e = 61344 edges
```

The generator records all matrices, sparse rows, logical supports, priors,
tool versions, upstream commit, samples, and preprocessing in `source/`.

## 2. Requirements

From the repository root:

```sh
./scripts/setup-bb144.sh
verilator --version
./mill --version
```

`setup-bb144.sh` creates `.venv`, installs the pinned Python requirements, and
the existing BB setup pins the upstream reference repository. Generated data
goes under `build/tutorials/bb144-parallel/`; it is not source code.

All settings can be overridden without editing a script:

```sh
OUT=build/my-run SHOTS_PER_P=100 WORKERS=2 SHARD_SIZE=25 \
  ./tutorials/BivariateBicycle144Parallel/run-all.sh
```

The checked-in defaults are `p=0.001,...,0.007`, 10,000 shots per probability, 50 fixed decoder
iterations, 500 shots per shard, and four concurrent simulator processes.

## 3. Run each research stage

### A. Construct the code, DEM, graph, priors, and samples

```sh
./tutorials/BivariateBicycle144Parallel/01-prepare.sh
```

This creates the seven-point sweep `p=0.001,...,0.007`, preserving correlated
X/Z syndromes and logical observables from one circuit-level Pauli process. The
seed and shot count are recorded in `source/sweep.json`. The tutorial streams
one probability point at a time and checks its vectorized singleton reduction
against the original scalar implementation, avoiding an all-shots memory
buffer without changing the mathematical experiment.

### B. Elaborate the graph-specialized RTL

```sh
./tutorials/BivariateBicycle144Parallel/02-emit-rtl.sh
```

The first problem supplies the common static topology. Chisel constructs one
CNU/VNU network and emits `artifact/rtl/StaticTannerArtifact.sv`. Pure Scala
also writes one complete 50-iteration golden trajectory at every `p`.

### C. Compile once and perform the exact preflight

```sh
./tutorials/BivariateBicycle144Parallel/03-build-and-check-rtl.sh
```

Verilator compiles the emitted artifact once. The resulting executable is then
reused to compare every marginal, correction, residual, convergence bit,
handshake, and iteration against Scala at all seven probabilities. Bulk Monte
Carlo simulation should not start unless this bit-exact preflight passes.

If an executable for byte-identical RTL is already available, the same stage
can exercise the attachment boundary without recompilation:

```sh
SIM=/absolute/path/to/VStaticTannerArtifact \
  ./tutorials/BivariateBicycle144Parallel/03-build-and-check-rtl.sh
```

### D. Run independent RTL shards

```sh
./tutorials/BivariateBicycle144Parallel/04-simulate-shards.sh
```

The format adapter streams the prepared benchmark into 140 immutable inputs:
20 shards at each of seven probabilities. SHA-256 hashes pin every input and
the simulator. Four workers each own a separate Verilator model. Successful
CSV is atomically published; reruns validate and skip finished work. Outputs
are merged only after checking local shot IDs, group values, row counts, and
global uniqueness.

Relevant files are:

```text
parallel/jobs.json      command, hashes, ranges, groups, cycle metadata
parallel/raw/*.csv      one independently restartable result per shard
parallel/run.json       measured simulator wall time and throughput
raw/shots.csv           deterministic merged records; analysis source of truth
```

### E. Analyze without running RTL

```sh
./tutorials/BivariateBicycle144Parallel/05-analyze.sh
```

This produces `results/results.csv`, `results/results.json`, the standalone
`results/logical_failure_rate.png`, and the two-panel
`results/logical_failure_and_cycles.png`. Analysis never imports or invokes
the hardware generator. The measured checked-in run is summarized in
`RESULTS.md`.

## 4. Attaching another generated RTL artifact

There are two supported boundaries.

### Same packed hardware ABI

If the attached SystemVerilog has top module `StaticTannerArtifact`, implements
the ports below, and was specialized for the exact graph in `sweep.json`, use:

```sh
RTL=/absolute/path/to/StaticTannerArtifact.sv \
  ./tutorials/BivariateBicycle144Parallel/03-build-and-check-rtl.sh
./tutorials/BivariateBicycle144Parallel/04-simulate-shards.sh
```

The packed ABI is:

| Direction | Port | Width |
|---|---|---:|
| input | `clock`, `reset`, `loadValid`, `stepValid` | 1 each |
| output | `loadReady`, `stepReady`, `resultValid`, `converged` | 1 each |
| input | `syndrome` | decoder `m` |
| input | `prior` | decoder `n * 4` |
| input | `stepControl` | 3 |
| output | `marginal` | decoder `n * 5` |
| output | `correction` | decoder `n` |
| output | `residual` | decoder `m` |

The exact preflight is the compatibility check: an artifact with a different
graph, packing convention, quantization, latency, or update semantics must not
be used merely because its port names happen to match.

### Arbitrary RTL ABI or another generator

Supply a small simulator harness that translates the project-specific ports to
this process contract:

```text
simulator --benchmark INPUT OUTPUT
```

It must return nonzero on error and write one CSV row per local shot, with a
local integer `shot` column containing exactly `0..count-1`. The BB analysis
also requires `p`, `converged`, and `logical_failure`; additional columns are
preserved. Point `SIM` at the executable:

```sh
SIM=/absolute/path/to/my_simulator CLOCK_CYCLES_PER_SHOT=102 \
  ./tutorials/BivariateBicycle144Parallel/04-simulate-shards.sh
```

For a different stimulus format, write only a small adapter that emits the
documented `rtl-shards.v1` manifest. Parallel scheduling, hashing, resumption,
validation, and merging remain unchanged. See
`benchmarks/rtl_shards/README.md` for the complete manifest contract.

## 5. Clock-cycle and logical-lifetime definitions

The present hardware always runs 50 iterations; convergence does not stop the
clock sequence. The Verilator harness applies

```text
1 reset clock + 1 load clock + 50 * (1 CNU + 1 VNU clock) = 102 clocks/shot.
```

This is an RTL protocol count, not post-place-and-route time. At a measured
FPGA frequency `f_clk`, decoder latency is `102 / f_clk`. Report an FPGA time
only after synthesis establishes `f_clk`.

Each physical shot represents `c=12` QEC syndrome cycles. If `F/S` is the
measured word-level logical failure probability, the plotted rate is

```text
p_L = 1 - (1 - F/S)^(1/c).
```

The corresponding geometric mean QEC lifetime is `1/p_L` syndrome cycles. The
computational work required to observe one failure in repeated independent
fixed-shot simulations is `102/(F/S)` decoder clocks. These are deliberately
reported as separate quantities: the latter is not the physical memory
lifetime. Wilson 95% intervals are transformed through both formulas.

## 6. Reproducibility rules

- Generate all random samples before sharding; worker count cannot change data.
- Keep `jobs.json`, `sweep.json`, raw shard CSV, and `run.json` with a result.
- Never compare two RTL revisions using silently regenerated samples.
- Treat `raw/shots.csv` as immutable evidence and regenerate plots from it.
- Report shots **per probability**, failures, confidence intervals, iteration
  count, clocks per shot, simulator wall time, worker count, and artifact hash.
- Distinguish non-convergence from logical failure; this experiment records
  both and defines failure only through the 24 logical-observable mismatch.
