# Measured 10,000-shot BB144 run

This is the measured result of the tutorial on the repository's development
machine. It is a behavioral Verilator measurement, not FPGA timing.

## Reproducibility record

| Item | Value |
|---|---:|
| code | `[[144,12,12]]` |
| simulated probabilities | `0.001,...,0.007` |
| shots per probability | 10,000 |
| total shots | 70,000 |
| decoder graph `(m,n,e)` | `(1872,17568,61344)` |
| fixed decoder iterations | 50 |
| decoder clocks per shot | 102 |
| represented QEC cycles per shot | 12 |
| total decoder clock work | 7,140,000 clocks |
| total represented QEC cycles | 840,000 cycles |
| workers / shard size | 8 / 500 shots |
| measured bulk workflow wall time | 8,831.96 s = 147.20 min |
| measured throughput | 7.926 shots/s |

Source preparation for the original eight-point input file took 101.77 s and
RTL emission plus Scala golden generation took 188.96 s. The emitted 78 MB
SystemVerilog had SHA-256
`75b24310196ebd66a7e03133bb2a2010be165f395f96fc1e3d125b34262ef300`,
identical to the already compiled artifact. That exact artifact's previously
measured one-time Verilator compilation took 1,078.22 s; reusing its executable
for the new golden data took 7.32 s to check all eight prepared trajectories.
The bulk run was deliberately stopped after `p=0.007` and the final manifest
contains no `p=0.008` jobs.

## Logical and cycle results

`P_word` is the fraction of shots with any mismatch among 24 logical
observables. `p_L = 1-(1-P_word)^(1/12)` is the logical failure rate per QEC
cycle. The two lifetime columns are different quantities: `1/p_L` is the mean
QEC syndrome-cycle lifetime, whereas `102/P_word` is decoder-clock work per
observed failure in repeated fixed-shot simulation.

| p | failures | converged | P_word | p_L / QEC cycle | expected QEC cycles | decoder clocks / failure |
|---:|---:|---:|---:|---:|---:|---:|
| 0.001 | 288 | 94.53% | 0.0288 | 0.0024323 | 411.14 | 3541.67 |
| 0.002 | 1327 | 79.32% | 0.1327 | 0.0117941 | 84.79 | 768.65 |
| 0.003 | 3292 | 55.65% | 0.3292 | 0.0327262 | 30.56 | 309.84 |
| 0.004 | 6726 | 21.76% | 0.6726 | 0.0888500 | 11.25 | 151.65 |
| 0.005 | 9000 | 6.02% | 0.9000 | 0.1745958 | 5.73 | 113.33 |
| 0.006 | 9896 | 0.47% | 0.9896 | 0.3164776 | 3.16 | 103.07 |
| 0.007 | 9994 | 0.04% | 0.9994 | 0.4610945 | 2.17 | 102.06 |

Wilson 95% intervals and unrounded values are in generated `results.csv` and
`results.json`. Hardware latency is `102/f_clk`; an absolute time must not be
reported until synthesis and implementation establish the FPGA clock rate.
