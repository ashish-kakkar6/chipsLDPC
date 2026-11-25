# chipsLDPC

Generate QEC decoder hardware from a Stim circuit and measure its failure rate
with Verilator. One experiment file selects the circuit, noise, decoder, and
sampling budget.

```{toctree}
:maxdepth: 1
:hidden:

Getting started <getting-started>
Reproduce the main results <reproduce-results>
Use your Stim circuit <custom-circuit>
Change the decoder <change-decoder>
Watch BP on the Steane code <walkthrough>
QEC decoding slides <decoding-slides>
Command and configuration reference <cli-reference>
Model and result reference <experiments/index>
QEC background <qec-background>
Hardware reference <architecture/index>
Verification <verification>
```

```sh
./chipsldpc setup
./chipsldpc doctor
./chipsldpc run experiments/smoke.toml --out runs/smoke
```

[Getting started](getting-started.md) covers installation and a small complete
circuit-to-RTL experiment at $p=0.003$.

## Main result

:::{figure} _static/bb144-results/legacy-v1/relay-budget.svg
:alt: Relay-BP word failure probability falls as the mean executed iteration count increases at physical error probability 0.003.

Relay-BP on the BB144 Z-check sector at $p=0.003$, with 20,000 shots per budget.
The y-axis counts decoder failure per 12-round memory shot. The x-axis is mean
executed BP iterations. These are archived results.
:::

[Run this profile or check the saved data](reproduce-results.md).

## Experiments and explanation

- [Use your Stim circuit](custom-circuit.md): supply a noisy circuit or a Python circuit factory.
- [Change the decoder](change-decoder.md): adjust a parameter, compare on shared samples, or prototype a Python decoder.
- [Watch BP on the Steane code](walkthrough.md): a three-minute animation of message passing and Relay scheduling.
- [QEC decoding slides](decoding-slides.md): the decoding section of the VTT talk.

The [model reference](experiments/bb144-model.md) defines the circuit noise,
observable comparison, and reported units. The [hardware reference](architecture/index.md)
connects the algorithm to the implementation.

## Cite

```bibtex
@misc{chipsLDPC,
  author = {Ashish Kakkar},
  title = {chipsLDPC: open source tools for real-time decoding of qLDPC codes},
  year = {2026},
  howpublished = {\url{https://github.com/ashish-kakkar6/chipsLDPC}}
}
```

Licensed under [Apache 2.0](../../LICENSE).
