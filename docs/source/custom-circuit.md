# Use your Stim circuit

The input is a noisy Stim circuit with `DETECTOR` and `OBSERVABLE_INCLUDE`
instructions. The circuit defines the code and syndrome extraction schedule.
Its detector error model supplies the decoding graph and priors. Samples come
from the circuit, including its physical noise correlations.

## A circuit file

Copy [the custom-circuit profile](../../experiments/custom-circuit.toml) and set
its circuit path:

```toml
[circuit]
kind = "stim"
path = "my-circuit.stim"

[noise]
p = 0.003

[sampling]
shots = 1000
seed = 14412

[decoder]
kind = "vanilla"
iterations = 30

[run]
backend = "verilator"
workers = 2
```

Save this as `experiments/my-code.toml`, with the circuit beside it, then run:

```sh
./chipsldpc run experiments/my-code.toml --out runs/my-code
```

Paths in the profile are relative to the profile file. A `.stim` file already
contains noise probabilities. The runner does not replace them with `[noise].p`.
Use a factory when you want `p` to control circuit construction.

## A circuit factory

Save `experiments/my_circuit.py`:

```python
import stim


def make_circuit(p):
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=3,
        rounds=3,
        after_clifford_depolarization=p,
        before_round_data_depolarization=p,
        after_reset_flip_probability=p,
        before_measure_flip_probability=p,
    )
```

Change the circuit section:

```toml
[circuit]
kind = "factory"
path = "my_circuit.py"
function = "make_circuit"
```

Keep `[noise].p = 0.003` and run the same command with a fresh output directory.
For a different code, replace the function body with your syndrome-extraction
circuit. The function must return a `stim.Circuit`.

## Inspect before compiling

```sh
./chipsldpc run experiments/my-code.toml --out runs/my-code --prepare-only
./chipsldpc run experiments/my-code.toml --out runs/my-code --emit-only
./chipsldpc run experiments/my-code.toml --out runs/my-code
```

Preparation reports the detector graph dimensions and writes the circuit,
model, and samples. Emission stops after generating RTL. The final command
continues through Verilator and reporting.

Each fault variable represents a detector/logical signature, not a data qubit.
The logical map is used to score corrections and is not supplied to the decoder.
A circuit with no observables cannot provide the logical failure measurement
requested here. Preparation currently requires deterministic detectors, undecomposed DEM errors,
and retained fault probabilities strictly between 0 and 1/2. Detector-free
logical faults are rejected. Hyperedges are retained, and singleton constraints
are eliminated exactly. Unsupported models fail before hardware compilation.

## Compare on the same samples

```sh
./chipsldpc run experiments/my-code.toml --out runs/my-code-variant \
  --samples runs/my-code/source
```

Reuse the saved source for decoder comparisons. Keep the circuit and noise
settings fixed. If you change either, prepare a new dataset.
