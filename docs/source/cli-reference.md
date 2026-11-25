# Command and configuration reference

Run `./chipsldpc --help` and `./chipsldpc run --help` for the accepted options.

| Command | Purpose |
| --- | --- |
| `setup` | Create the local Python environment and install dependencies |
| `doctor` | Check tools before starting work |
| `run PROFILE` | Prepare samples, emit RTL, simulate, and report |
| `plot RUN_DIR` | Rebuild plots from an existing run |
| `results check` | Check the frozen documentation results without simulation |
| `results plot --out DIR` | Redraw frozen results in a separate directory |

## Run options

| Option | Meaning |
| --- | --- |
| `--out DIR` | Keep all outputs for this experiment together |
| `--shots N` | Override the profile's shot count |
| `--workers N` | Limit parallel simulation work |
| `--backend verilator` | Run generated SystemVerilog in Verilator |
| `--backend python` | Run the software decoder |
| `--samples RUN_DIR/source` | Reuse a saved sample corpus |
| `--prepare-only` | Stop after circuit/model and sample preparation |
| `--emit-only` | Stop after RTL generation |

An unchanged run resumes. A different configuration in an existing output
directory is rejected. Choose a new output path for a changed experiment.
Changing `workers` or `compile_jobs` is allowed when resuming. Without `--out`, the runner
uses `runs/<profile-name>-<identity>` and prints the path. It records resolved
settings and stage completion with its outputs.

## Profile fields

Profiles are TOML files. Paths are relative to the profile.

| Section | Fields |
| --- | --- |
| `circuit` | `kind = "builtin"`, `name`, `distance`, `rounds`; or `kind = "stim"`, `path`; or `kind = "factory"`, `path`, `function` |
| `noise` | `p` or a `probabilities` list passed to built-in circuits and factories; circuit files carry their own noise |
| `sampling` | `shots`, `seed`, `verification_shots` |
| `decoder` | `kind = "vanilla"`, `iterations` or `budgets`; or `kind = "relay"`, `initial_iterations`, `relay_iterations`, `relay_legs` or `budgets`, `solutions`, `seed_offset`; or `kind = "python"`, `path`, `function`, `iterations` |
| `run` | `backend`, `workers`, `compile_jobs`, `shard_size` |

Built-in circuit names are `repetition`, `surface`, and `bb144`. The supplied
profiles are the shortest complete examples. A Relay total budget
must be `initial_iterations + R * relay_iterations` for a nonnegative integer
`R`. Here `R` counts legs after the initial leg.

## Python decoder contract

The callable has this signature:

```python
def decode(row_ones, priors, syndrome, max_iterations):
    # Return one correction bit per DEM fault-signature column.
    return {"correction": correction, "iterations": iterations}
```

`row_ones` is a list of detector-check supports. `priors` is a list of
floating-point LLRs `log((1-p)/p)`, and `syndrome` is one bit per check. Legacy
corpora without saved DEM probabilities supply quantized priors divided by their
recorded scale instead.
`max_iterations` is the current budget. A result may also be just the correction
bit list; iteration statistics are then unavailable. The harness checks parity
and logical outcomes independently. Actual observable bits are never passed to
the callable.

The supplied [example decoder](../../experiments/decoders.py) calls
`chipsldpc.prototype.minsum_decode(..., scale=0.5)`. Its baseline scale is 0.75.
The Python backend is a floating-point algorithm prototype, not a bit-exact RTL
model. It currently supports normalized min-sum and user callables, not Relay.

## Result meaning

Report failure count and shots with a 95% interval. The primary estimate is the
probability of decoder failure per memory shot, including nonconvergence.
Keep backend labels when comparing results. RTL cycle counts require a measured
hardware clock before they can be interpreted as physical latency.
