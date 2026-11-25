# Getting started

The first experiment uses a small repetition-code memory circuit,
circuit-level noise at $p=0.003$, and the vanilla min-sum RTL decoder.

With Git installed, obtain the source:

```sh
git clone https://github.com/ashish-kakkar6/chipsLDPC.git
cd chipsLDPC
```

Run the commands below from this repository directory.

## Install

You need Python 3.12 or newer, Java 17 or newer, Verilator, a C++ compiler, and
Make. Mill downloads the Scala build dependencies on first use.

On macOS with Homebrew:

```sh
brew install python@3.12 openjdk@17 verilator
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
```

Install the Xcode command-line tools with `xcode-select --install` if no C++
compiler is installed. On Ubuntu 24.04:

```sh
sudo apt-get update
sudo apt-get install git python3.12 python3.12-venv openjdk-17-jdk verilator build-essential
```

Then prepare the repository's Python environment and check the tools:

```sh
./chipsldpc setup
./chipsldpc doctor
```

If `python3` names an older Python, select the installed interpreter explicitly:

```sh
CHIPSLDPC_PYTHON="$(command -v python3.12)" ./chipsldpc setup
```

The first run needs network access to obtain build dependencies. The doctor
command reports missing tools before a simulation starts.

## Run one complete experiment

```sh
./chipsldpc run experiments/smoke.toml --out runs/smoke
```

The runner prepares the circuit and detector model, samples detectors and
observables, generates RTL, builds Verilator, simulates each shot, and writes a
CSV and plot. It prints progress and the output paths.

The circuit's detector model fixes the hardware graph. A new graph requires
new RTL. Syndromes, priors, and stopping limits are inputs to that hardware.

The small shot count is a workflow check. Zero observed failures is an upper
bound on the failure probability, not evidence of zero error rate.

As a local build measurement, on macOS arm64 with Scala dependencies cached and
two compilation jobs, RTL emission plus Verilator compilation took about 7 s
for this example and 19 s for the surface-code example. These times exclude
preparation, reference checks, simulation, and plotting. First-time dependency
downloads take additional time; timing fields are saved in `run.json`.

## Read the result

The primary quantity is **decoder failure probability per memory shot**:
nonconvergence or a mismatch between predicted and sampled logical observables.
Read the failure count, shot count, and 95% interval together. The report also
counts nonconvergence and observable mismatches. Those categories can overlap.

A run directory retains the circuit/model and samples in `source/`, emitted
hardware in `artifact/`, raw simulation outputs, and plots under `results/`.
The primary files are `results/summary.csv`, `results/summary.json`, and
`results/logical_failure.png` (also PDF). To redraw a completed run:

```sh
./chipsldpc plot runs/smoke
```

Repeating an unchanged run resumes completed work. Use a new `--out` directory
when changing scientific settings. Existing results are never silently deleted.

## Next experiment

```sh
./chipsldpc run experiments/surface-smoke.toml --out runs/surface-smoke
./chipsldpc run experiments/bb144-p003.toml --out runs/bb144-p003
```

The surface-code example checks another graph. The BB144 profile is the
[substantial result experiment](reproduce-results.md). For your own code, follow
[Use your Stim circuit](custom-circuit.md).

If simulation uses too much memory, reduce its worker count:

```sh
./chipsldpc run experiments/smoke.toml --out runs/smoke --workers 1
```

For compilation, set `compile_jobs = 1` in the profile's `[run]` section.
Worker and compilation counts can change when resuming the same experiment.

For a vanilla min-sum prototype, `--backend python` skips RTL generation and
Verilator. This backend uses floating-point normalized min-sum, not the integer
RTL arithmetic, and does not implement Relay. Its outputs are marked as Python
simulation results. See [Change the decoder](change-decoder.md).
