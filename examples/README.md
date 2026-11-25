# Examples

Use the [experiment runner](../docs/source/getting-started.md). Runnable profiles
live in `experiments/` and share one command:

```sh
./chipsldpc run experiments/smoke.toml --out runs/smoke
./chipsldpc run experiments/bb144-p003.toml --out runs/bb144-p003
```

[Use another circuit](../docs/source/custom-circuit.md) ·
[Change the decoder](../docs/source/change-decoder.md) ·
[Reproduce results](../docs/source/reproduce-results.md)

The older `BivariateBicycle144*` entry points are compatibility wrappers.
Leaf RTL inspection remains available through `scripts/emit.sh`; focused tests
are listed in the [verification reference](../docs/source/verification.md).
