# Change the decoder

Use a profile for parameters, Python for an algorithm prototype, and the Chisel
implementation when you want that algorithm in RTL.

## Change a stopping rule

Copy `experiments/bb144-p003.toml` to `experiments/my-relay.toml`. Change the Relay
candidate target in `[decoder]`:

```toml
kind = "relay"
initial_iterations = 60
relay_iterations = 60
solutions = 1
budgets = [60, 120, 180, 300, 540, 1020, 2040, 4080]
seed_offset = 0
```

Run the baseline, then the variant on the saved samples:

```sh
./chipsldpc run experiments/bb144-p003.toml --out runs/baseline
./chipsldpc run experiments/my-relay.toml --out runs/variant \
  --samples runs/baseline/source
```

Compare failure counts and intervals alongside executed iterations. Keep the
sample corpus, quantization, and other settings fixed when studying one change.
A smaller trial with `--shots 100` checks the workflow but is too small to resolve
rare logical failures.

## Prototype an algorithm in Python

The Python backend uses floating-point normalized min-sum, which is a distinct
numerical algorithm from the quantized RTL. It does not implement Relay or
provide bit-exact hardware checks. Run a baseline and the supplied scale variant
on the same small corpus:

```sh
./chipsldpc run experiments/python-baseline.toml --out runs/python-baseline
./chipsldpc run experiments/decoder-variant.toml --out runs/python-variant \
  --samples runs/python-baseline/source
```

The variant changes normalized min-sum's check-message scale from 0.75 to 0.5.
For your own implementation, select a Python callable:

```toml
[decoder]
kind = "python"
path = "decoders.py"
function = "decode"

[run]
backend = "python"
workers = 1
```

The [configuration reference](cli-reference.md#python-decoder-contract) defines
the callable's inputs and outputs. It receives detector-model data and the
syndrome, never the sampled logical answer. Use the same saved corpus to compare
it with an existing decoder.

A Python callable is an algorithm experiment. Generating its RTL requires an
implementation in Chisel; the runner does not translate Python decoder code.

## Implement the change in RTL

| Change | Source |
| --- | --- |
| Check update / magnitude scaling | [CheckNode.scala](../../src/main/scala/chipsldpc/CheckNode.scala), [Arithmetic.scala](../../src/main/scala/chipsldpc/Arithmetic.scala) |
| Variable update / saturation | [VariableNode.scala](../../src/main/scala/chipsldpc/VariableNode.scala) |
| Relay bias | [RelayBias.scala](../../src/main/scala/chipsldpc/RelayBias.scala) |
| Leg scheduling / candidate selection | [RelayBpDecoder.scala](../../src/main/scala/chipsldpc/RelayBpDecoder.scala) |
| Independent integer reference | [Reference.scala](../../src/test/scala/chipsldpc/Reference.scala) |

Update the corresponding reference and focused tests, then run a small RTL
experiment before a large comparison. The [architecture](architecture/index.md)
explains the equations, fixed-point conventions, and two-clock iteration.
[Verification](verification.md) lists the focused suites.
