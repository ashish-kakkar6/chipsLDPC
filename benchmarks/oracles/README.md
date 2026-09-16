# External decoder oracles

`trmue_relay.py` runs one deterministic fixture through the public
[`trmue/relay`](https://github.com/trmue/relay) implementation. It never clones,
installs, or accesses the network. The caller must provide a pristine checkout at
commit `d185194ba0cb4101ced4340d82b2ee6d42f225f0` and run the adapter in a Python
environment where that checkout has been installed editable:

```sh
export RELAY_REF_DIR=/path/to/relay
python -m pip install -e "$RELAY_REF_DIR"
python benchmarks/oracles/trmue_relay.py --self-test --pretty
python benchmarks/oracles/trmue_relay.py \
  benchmarks/oracles/fixtures/repetition_beta_int.json --pretty
```

The input schema is `trmue-relay-oracle.v1` (the `schema` field is optional):

```json
{
  "schema": "trmue-relay-oracle.v1",
  "check_rows": [[0, 1], [1, 2]],
  "syndrome": [1, 1],
  "priors": [0.1, 0.1, 0.1],
  "prior_kind": "error_probability",
  "legs": [
    {"gamma": 0.1, "max_iterations": 10},
    {"beta_int": [6, 6, 5], "max_iterations": 5}
  ],
  "decoder": {"dtype": "f64", "alpha": 1.0},
  "stopping": {"criterion": "all", "nconv": 1},
  "expected": {"success": true, "correction": [0, 1, 0]}
}
```

Use either dense `check_matrix` rows or sparse `check_rows`; the latter contain
variable indices. `priors` are error probabilities by default. Set `prior_kind`
to `llr` for values of `log((1-p)/p)`. Each leg specifies either `gamma` or
real-valued `beta = 1-gamma`, or the RTL's 4-bit `beta_int = 8*(1-gamma)`, as a
scalar or one value per variable. `beta_int` is converted to the floating-point
oracle by `gamma = 1-beta_int/8`; this comparison remains algorithmic rather
than bit-exact because the oracle uses a full multiplier. Leg zero is the initial
ordered-memory run and can only have a scalar coefficient; `gamma: null` selects
vanilla BP. All later legs must currently have the same `max_iterations`, because
the reference Python API exposes one shared `set_max_iter`.
When present, `expected` makes the adapter fail unless the pinned reference
returns that success flag and correction.

The adapter prepends the dummy explicit-gamma row required by the pinned source:
the upstream relay loop indexes rows with `set=1..num_sets`, so passing only the
requested rows would shift the schedule and wrap the last leg to row zero. The
default stopping criterion is `all`, ensuring every scheduled leg is attempted;
`decode_inner` may still stop an individual leg as soon as its syndrome converges.
