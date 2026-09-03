# BB144 FPGA minimum-evidence plan

## Outcome

Get the first defensible FPGA numbers for the existing `chipsLDPC` BB144
benchmark with the least new code:

1. mapped and post-route resources for the unchanged decoder core;
2. post-route setup/hold timing on one exact FPGA part;
3. one on-board, self-checking execution of the same golden vector; and
4. measured decoder clock cycles, kept separate from host-to-FPGA I/O time.

The fastest honest path is **not** to integrate chipsLDPC into Helios. Helios is
a distributed union-find surface-code decoder; chipsLDPC BB144 is a static
min-sum Tanner-graph decoder. Their protocols, graph state, and outputs are not
compatible. Helios is useful here only as evidence for a Xilinx/Vivado/VCU129
workflow and for the pattern of keeping a small board wrapper around a core.

Current status: the software/golden baseline passes and the OOC flow is ready,
but this Mac has no `vivado` executable in `PATH`. Therefore this folder does
not claim mapped resource or routed timing numbers yet. Run Phases 1–2 on the
licensed Vivado host after confirming the exact FPGA part.

## Audit snapshot

| Item | Observed value |
|---|---:|
| Local workload | `benchmarks/rtl_shards` BB144 example |
| Actual synthesis input | `StaticTannerArtifact.sv` |
| Code | `[[144,12,12]]` bivariate bicycle |
| Decoder graph `(m,n,e)` | `(1872, 17568, 61344)` |
| Check degree | 16, 25, or 35 |
| Variable degree | 2 through 6 |
| Iterations | 50 fixed |
| Core protocol | one load, then one CNU and one VNU clock per iteration |
| Clock count | 100 clocks from accepted load to final result; 102 including the benchmark driver's reset and load clocks |
| Emitted RTL | 82,062,871 bytes; 1,358,801 lines |
| RTL SHA-256 | `75b24310196ebd66a7e03133bb2a2010be165f395f96fc1e3d125b34262ef300` |
| Packed top-level interface | about 179,435 signal bits |
| Current chipsLDPC Git commit | `55ad8c58e5be9d890755699e34de17b42c428e8c` plus uncommitted/untracked work |
| Temporary Helios clone | `/private/tmp/helios-scalable-qec.MYQ2o2/repo` at `622d85dac2c78006e1e2aea940725ef800d853c0` |
| Local FPGA tool status | Verilator and Yosys present; Vivado absent from `PATH` |

`benchmarks/rtl_shards` is a host-side Verilator scheduler. It does not contain
an FPGA top. The FPGA candidate is the immutable generated RTL at either of
these currently byte-identical locations:

```text
build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv
build/tutorials/bb144-parallel/artifact/rtl/StaticTannerArtifact.sv
```

The top ABI is:

| Direction | Port | Width |
|---|---|---:|
| input | `clock`, `reset`, `loadValid`, `stepValid` | 1 each |
| input | `syndrome` | 1,872 |
| input | `prior` | 70,272 |
| input | `stepControl` | 3 |
| output | `loadReady`, `stepReady`, `resultValid`, `converged` | 1 each |
| output | `marginal` | 87,840 |
| output | `correction` | 17,568 |
| output | `residual` | 1,872 |

The Scala structure declares about 639,507 bits of stored state before Vivado
optimization:

```text
CNU result and syndrome state = 9*m + 2*e  = 139,536 bits
VNU prior and result state    = 11*n + 5*e = 499,968 bits
controller state                              3 bits
```

That is a capacity warning, not a substitute for synthesis. It is already more
than the ZCU106's 460,800 CLB flip-flops, so the exact fully parallel artifact
should not be targeted to ZCU106. The first sensible default from the Helios
context is the VCU129, whose exact Vivado part string is
`xcvu29p-fsga2577-2L-e`. VU29P has four SLRs, so per-SLR utilization and SLR
crossings are mandatory evidence, not optional diagnostics.

Relevant AMD references:

- [VCU129 board/device description](https://docs.amd.com/api/khub/documents/EqujCv0b~fgjVjTwGTAx3g/content)
- [AMD/Xilinx VCU129 Vivado board file](https://github.com/Xilinx/XilinxBoardStore/blob/2022.2/boards/Xilinx/vcu129/production/1.0/board.xml)
- [ZCU106 resources](https://docs.amd.com/api/khub/documents/FiJhhOVPF8Ijqstd8bPc6A/content)
- [Vivado out-of-context synthesis](https://docs.amd.com/r/2021.1-English/ug835-vivado-tcl-commands/synth_design)
- [OOC timing constraints](https://docs.amd.com/r/en-US/ug905-vivado-hierarchical-design/Timing-Constraints)
- [Vivado implementation reports](https://docs.amd.com/r/en-US/ug904-vivado-implementation/Step-8-Run-Required-Reports)

## What counts as a real result

| Claim | Minimum acceptable evidence |
|---|---|
| RTL behavior | Existing Verilator executable matches Scala golden data for all 50 iterations |
| FPGA resource use | Vivado synthesis for the exact part and exact RTL hash |
| Physical resource use | Successful placement plus post-route hierarchical utilization |
| Timing estimate | Completed route, zero internal unrouted nets, constrained clock, WNS/TNS and WHS/THS |
| Achieved clock | A routed run with nonnegative setup and hold slack |
| Hardware function | Programmed board returns the expected final result on repeated resets |
| Decoder latency | Hardware counter from load acceptance to final `resultValid` |

Yosys generic cells and post-synthesis Vivado timing are useful smoke signals,
but neither is the requested FPGA resource/timing result. Absolute time is
`cycles / f_clk` only after routed timing establishes `f_clk`.

## Minimal maintained files

Keep the generated 82 MB RTL where it is; do not copy or edit it.

```text
fpga_bb144_minimal/
  PLAN.md             # this plan and the acceptance contract
  run_ooc.tcl         # current core synthesis/place/route flow
  core_ooc.xdc        # current internal core timing model

# Add only after the OOC fit gate passes:
  make_selftest.py
  rtl/bb144_bist_top.sv
  constraints/<actual-board>.xdc
  build_board.tcl

build/fpga-bb144/     # generated checkpoints, reports, vectors, bitstream
```

This is four new maintained implementation files for board proof. There is no
AXI subsystem, processor software, PCIe driver, DDR controller, or imported
Helios block design in the minimal path.

## Phase 0 — freeze and recheck the existing artifact

Do not regenerate the decoder just to start synthesis. The current artifact is
already present and byte-identical in the generated example and the 70,000-shot
tutorial.

From the chipsLDPC root:

```sh
.venv/bin/python3 -m unittest benchmarks/rtl_shards/test_workflow.py

build/generated/bivariate-bicycle-144/verification/p0_0010/obj_dir/VStaticTannerArtifact \
  build/generated/bivariate-bicycle-144/verification/p0_0010/golden.txt \
  /tmp/bb144-result.json compact

shasum -a 256 \
  build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv \
  build/generated/bivariate-bicycle-144/source/benchmark.txt \
  build/generated/bivariate-bicycle-144/verification/p0_0010/golden.txt
```

Current local evidence:

- the workflow's two unit tests pass under the repository `.venv`;
- the existing RTL executable matches all 50 Scala golden iterations; and
- the first `p=0.001` verification vector is nontrivial (syndrome weight 46)
  and converges.

Pin that vector rather than regenerating it with a different shot count:

```text
problem.json SHA-256 = 4b2560c5c1be311fa64d445f5711ef28ef6abe6a99aa4c042dcdae180de2ac28
golden.txt SHA-256   = 9ec3c8b19ef1209a68fc7ea3ed999bd24e1536693a0a246dcc75d24ad072df03
```

The seeded Stim stream depends on the requested batch size in this workflow.
For example, regenerating with `shots=1` is not guaranteed to recreate the
current 100-shot run's first vector. Either preserve the files above or record
and use the newly generated problem/golden pair together.

If the artifact must be recreated on another machine, run only tutorial stages
1–3. Do not run the 70,000-shot simulation for FPGA resource/timing work:

```sh
OUT=build/fpga-bb144/repro P_VALUES=0.001 SHOTS_PER_P=1 \
  ./tutorials/BivariateBicycle144Parallel/01-prepare.sh
OUT=build/fpga-bb144/repro \
  ./tutorials/BivariateBicycle144Parallel/02-emit-rtl.sh
OUT=build/fpga-bb144/repro \
  ./tutorials/BivariateBicycle144Parallel/03-build-and-check-rtl.sh
```

This makes a new self-consistent one-shot problem/golden pair; it does not
promise to reproduce the pinned 100-shot run's first vector.

Create a provenance text file beside every FPGA run containing:

- chipsLDPC commit and `git status --porcelain`;
- RTL, benchmark, problem, and golden SHA-256 values;
- Java, firtool, Verilator, and Vivado versions;
- exact `PART`, speed grade, clock period, uncertainty, and implementation
  directives; and
- host name, OS, CPU count, memory, start/end time, and exit status.

The Git commit alone is insufficient because the current benchmark and related
source are untracked or modified.

Acceptance: exact RTL/golden check passes and the recorded RTL hash is the hash
given to Vivado.

## Phase 1 — fast flow smoke test

Run the same OOC script on the small Steane core before spending hours on the
82 MB BB144 source. This tests the Vivado install, target part, SystemVerilog
reader, constraints, and report commands. It is not a BB144 estimate.

```sh
mkdir -p build/fpga-bb144/steane-ooc

vivado -mode batch \
  -log build/fpga-bb144/steane-ooc/vivado.log \
  -journal build/fpga-bb144/steane-ooc/vivado.jou \
  -source fpga_bb144_minimal/run_ooc.tcl -tclargs \
  build/generated/static-steane/StaticTannerDatapath.sv \
  xcvu29p-fsga2577-2L-e 10.000 \
  build/fpga-bb144/steane-ooc StaticTannerDatapath
```

Acceptance: Vivado recognizes the part, completes route, and emits every report
without Tcl or constraint errors.

## Phase 2 — exact BB144 OOC resource and internal timing pass

Assumption for the first run:

```text
board:  VCU129
part:   xcvu29p-fsga2577-2L-e
tool:   one pinned Vivado version, preferably 2023.2
clock:  10.000 ns (100 MHz), 0.200 ns uncertainty
flow:   default synth/opt/place/phys_opt/route directives
```

If the physical board is different, replace the part before running. Never
compare utilization percentages or timing across different part/speed-grade
strings without labeling them separately.

```sh
mkdir -p build/fpga-bb144/vcu129-10ns-ooc

vivado -mode batch \
  -log build/fpga-bb144/vcu129-10ns-ooc/vivado.log \
  -journal build/fpga-bb144/vcu129-10ns-ooc/vivado.jou \
  -source fpga_bb144_minimal/run_ooc.tcl -tclargs \
  build/generated/bivariate-bicycle-144/artifact/rtl/StaticTannerArtifact.sv \
  xcvu29p-fsga2577-2L-e 10.000 \
  build/fpga-bb144/vcu129-10ns-ooc StaticTannerArtifact
```

`run_ooc.tcl` uses `-mode out_of_context`, so Vivado does not insert roughly
179,000 I/O buffers. Its XDC deliberately false-paths the packed boundary and
measures genuine register-to-register core paths. This makes the first run a
resource result and a preliminary **internal-core** timing result. The complete
board route in Phase 3 is the final interface-aware timing result.

Required reports are already emitted:

```text
checkpoints/post_synth.dcp
checkpoints/post_route.dcp
reports/post_synth_util.rpt
reports/post_synth_timing.rpt
reports/post_route_util.rpt
reports/post_route_timing.rpt
reports/reg_to_reg_timing.rpt
reports/route_status.rpt
reports/post_route_check_timing.rpt
reports/clock_util.rpt
reports/congestion.rpt
reports/high_fanout_nets.rpt     # when supported by the Vivado version
reports/slr_util.rpt             # when supported by the Vivado version
reports/slr_crossing.rpt         # when supported by the Vivado version
reports/drc.rpt
reports/methodology.rpt
run_metadata.txt
vivado.log
```

### Fit gate

Stop before board-wrapper work if any of these is true:

- synthesis reports more than 100% of any device resource;
- the design contains black boxes, inferred latches, or missing clocks;
- placement fails;
- route does not complete; or
- route status has internal unrouted nets.

Record LUT, LUTRAM, FF, CARRY, BRAM, URAM, DSP, clock-buffer use, global
percentages, per-SLR percentages, and the largest three hierarchy consumers.
Utilization above roughly 80% globally or severe imbalance in one SLR is a
routing-risk flag, even if arithmetic capacity says “fits.” Make one baseline
route before adding pblocks or trying many seeds.

### Timing gate

A frequency is “achieved” only when routed setup and hold slack are both
nonnegative. Record:

- WNS/TNS and count of failing setup endpoints;
- WHS/THS and count of failing hold endpoints;
- worst 20 startpoints/endpoints, logic levels, and path groups;
- net delay versus cell delay;
- high-fanout control nets; and
- SLR crossings on critical paths.

After the first route, use only one confirmation run:

```text
estimated critical period = requested period - routed WNS
guarded candidate period  = 1.05 * estimated critical period
unconstrained Fmax estimate (MHz) = 1000 / estimated critical period
```

Routing changes when the constraint changes, so the arithmetic value alone is
not a result. Reroute once at the guarded candidate period and require
nonnegative setup and hold slack. If that route closes, `1000 / guarded
candidate period` is a conservative achieved frequency for that run, not a
proof of the design's absolute Fmax. More seeds/strategies are optimization
work, not part of the minimum evidence pass.

If OOC routing hits a boundary-model or routing limitation, keep the synthesis
resource result and proceed directly to the registered BIST shell. Do not claim
the OOC timing as final.

## Phase 3 — smallest credible on-board proof

Only start this phase after the exact core fits.

### Test vectors

Use the pinned `p0_0010` vector above for the minimum board proof. Its expected
final state is converged, residual weight zero, correction weight 16, and
predicted logical word `0x062242`.

Two optional vectors cover different decoder outcomes. Build each as a separate
wrapper/bitstream so a runtime selector does not create a huge input mux:

| Vector | Outcome | Problem SHA-256 | Golden SHA-256 |
|---|---|---|---|
| `p0_0030` | nonconverged, logically correct | `6436cdf0e5d8e53919302d11274abadef7a93d9c55f9fca83b112baaf09c80ba` | `b56c8dcae28292c3ea0d08bb9cf40b63bd7d27919c660f9a20bcc214e0bf0a91` |
| `p0_0040` | nonconverged, intentional logical failure | `0eae5db1e41ec3983397b50286def954ac2dbc057849bf3d3d13e5a8b9cc218e` | `1ab20a2852e5f006fd4275a65d46e2961dd2a34bb4d89231492848713b21ccee` |

`make_selftest.py` reads one selected `problem.json` and the final record in
its matching `golden.txt`, then writes packed generated files under
`build/fpga-bb144/selftest/`. Giant hand-written constants are forbidden.
Packing must be checked by wrapper-level RTL simulation before bitstream
generation.

### BIST shell

`bb144_bist_top.sv` has only a board clock/reset boundary and these internal
status values:

```text
test_id, busy, done, pass, fail, decoder_cycles, harness_cycles
```

Expose status through one small ILA, or through existing board LEDs if the
actual board XDC already names them. Auto-start after reset; do not build a host
driver for the first proof.

The FSM is exactly:

1. load the packed syndrome and prior from generated ROM/shift storage;
2. hold `loadValid` until `loadReady`, then record the acceptance edge;
3. for iterations 1 through 50, drive `stepControl=min(iteration,7)`;
4. hold `stepValid` until `stepReady`;
5. wait for the corresponding `resultValid` before issuing the next step;
6. on iteration 50, compare complete `correction`, `residual`, and `converged`
   against the final golden record in registered chunks;
7. optionally compute the benchmark's 24 logical-observable parities and
   compare them to the golden decoder prediction, never to the physical
   `actual_observables` label; and
8. latch `done/pass/fail` until reset.

The existing Verilator preflight remains responsible for every intermediate
`marginal` and every iteration. The board BIST proves that the placed core
clocks and produces the benchmark-relevant final result.

For the board build, re-read the unchanged generated SV beside the wrapper and
mark only the decoder instance `KEEP_HIERARCHY` and `DONT_TOUCH`. Do **not**
import the Phase-2 OOC DCP: it carries boundary false paths that could hide the
wrapper-to-core paths this phase must measure. Report the OOC core and the full
BIST design separately; never quote wrapper-inflated totals as core resources.
As a backstop, compare hierarchical LUT/FF counts for the board build's decoder
instance with the OOC core. If the instance shrinks materially, the fixed-vector
build is not valid decoder-on-FPGA evidence.

Use the actual board clock buffer and XDC in this phase. Start at a conservative
frequency below the passing routed period, then run the full board
implementation and save interface-aware timing reports. Do not generate a
bitstream with unconstrained pins or timing paths.

Acceptance:

- full board design completes route with nonnegative setup and hold slack;
- no error-level DRC and no unconstrained sequential endpoints;
- programming succeeds;
- the pinned `p0_0010` vector produces `done=1`, `pass=1`, `fail=0` on three
  resets;
- load acceptance to the 50th `resultValid` is exactly 100 clock periods;
- the benchmark-driver convention remains 102 rising edges including reset and
  load; and
- `.bit`, optional `.ltx`, utilization/timing/route reports, ILA capture, and
  provenance are archived together.

At 100 MHz these two explicitly different latency numbers are 1.00 us and
1.02 us. Do not include ROM loading, JTAG, UART, or host transfer time in the
decoder-kernel number.

## Phase 4 — optional live benchmark transport

This is not required for first resource/timing evidence. If multiple live shots
are needed after BIST passes, keep one probability point per bitstream or cache
its prior vector. Priors are common to every shot at a given `p`, so only the
1,872-bit syndrome must change per shot: 59 32-bit words. Return only the 24
logical parities, convergence, and cycle count.

Add the smallest transport already native to the actual board (AXI-Lite on a
Zynq board, PCIe on an accelerator card, or UART for very low volume). Do not
choose the transport before the board is named, and report its loading time
separately from the 100-cycle decoder latency.

## Failure decisions

| Observation | Next action |
|---|---|
| Small Steane run fails | Fix tool/part/Tcl setup; do not launch BB144 |
| BB144 synthesis exceeds capacity | Record “exact static BB144 does not fit on PART”; stop |
| Synthesis fits, placement fails | Inspect control sets and per-SLR imbalance once |
| Route fails from congestion/crossings | Record no valid timing; stop the minimal path |
| Route succeeds with negative WNS | One rerun at the guarded inferred period |
| OOC passes, board top fails | Diagnose only clock/reset/XDC/BIST boundary first |
| BIST passes | Archive evidence; only then consider multi-shot transport |

If the exact static design cannot fit or route, the next honest project is a
BRAM-backed/time-multiplexed decoder or an SLR/multi-FPGA graph partition. That
is an architectural redesign and must not be disguised as a quick wrapper fix.

## Low-entropy rules

- Never edit or duplicate generated `StaticTannerArtifact.sv`.
- Key every result by its RTL SHA-256, not only Git commit.
- One Tcl flow, one target part, one baseline strategy, one confirmation clock.
- Keep OOC core reports separate from BIST/full-board reports.
- No internal false paths or multicycle exceptions on CNU-to-VNU or VNU-to-CNU
  paths; those are real one-cycle transfers.
- No floorplan, retiming, resource sharing, or seed sweep before the baseline.
- Do not import Helios RTL, block designs, absolute paths, or stale project Tcl.
- A failed fit/route is a valid minimal result; do not silently shrink the
  graph, prune outputs, or substitute the Steane example.
