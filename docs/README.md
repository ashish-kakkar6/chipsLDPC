# Documentation

The site uses Sphinx and MyST Markdown.

From the repository root:

```sh
python3 -m venv .venv-docs
./.venv-docs/bin/python -m pip install -r requirements-docs.txt
make -C docs html PYTHON="$(pwd)/.venv-docs/bin/python"
```

Open `docs/_build/html/index.html` after the build completes.

## Scientific writing skeleton

The first-pass draft integrates presentation slides 16–20 and 22–25.
Equations, figures, code links, citations, and archived result metadata are
populated. Search for `author-placeholder` in `docs/source` to find the
scientific prose still to write. Replace the relevant **Author text** box with
your explanation, keeping equation/figure labels and source links stable.

| Content | Editable page |
| --- | --- |
| Priors, posterior, bitwise decoding, LLRs, message rules | `source/qec-background.md` |
| CNU and VNU hardware | `source/architecture/bp-decoder.md` |
| Relay bias and legs | `source/architecture/relay-bp.md` |
| Circuit model and DEM sizes | `source/experiments/bb144-model.md` |
| Vanilla, Relay, and iteration-budget plots | `source/experiments/bb144-results.md` |

## Figures and archived data

Run from the repository root. The diagram sources are small Python SVG
generators; no TeX installation is required. Outputs have text alternatives,
and editable mathematics remains in MyST rather than in screenshots.

```sh
python3 docs/figures/build_tanner.py
python3 docs/figures/build_architecture.py
```

The three archived plots use the immutable, self-contained manifest and CSVs
under `docs/source/_static/bb144-results/legacy-v1/`. To regenerate them, install
the optional plotting dependency in a Python environment, then run:

```sh
.venv-docs/bin/python -m pip install -r docs/requirements-figures.txt
MPLCONFIGDIR=/tmp/chipsldpc-mpl .venv-docs/bin/python docs/figures/publish_bb144.py
```

The publisher verifies the archived inputs before plotting. It does not run
an experiment or read mutable results from `build/generated`. Preserve dataset
identity when adding a new experiment: use another directory and a new manifest.

## Review checks

```sh
make -C docs check-assets PYTHON="$(pwd)/.venv-docs/bin/python"
make -C docs html PYTHON="$(pwd)/.venv-docs/bin/python"
make -C docs linkcheck PYTHON="$(pwd)/.venv-docs/bin/python"
```

Asset checks use only the Python standard library; normal HTML builds use the
checked-in figures. Inspect the rendered math, figure captions,
data downloads, source links, and author prompts on wide and narrow screens.
External link checking needs network access; temporary publisher blocks should
be reviewed independently from local build or asset failures.

Use equation/figure anchors for internal cross-references. Link each implemented
quantity or equation to the function or named signal that computes it, using a
repository-relative Markdown link with a verified source line, for example:

```md
[`VariableLogic.apply`](../../../src/main/scala/chipsldpc/VariableNode.scala#L8)
```

The documentation build renders linked code from the current checkout as
syntax-highlighted pages with line anchors. The build rejects missing files or
line numbers beyond the end of a file. Recheck the symbol at that line when
editing code; a valid line number alone does not establish scientific accuracy.

Cite primary papers beside theoretical equations. Distinguish the probabilistic
model from the quantized min-sum approximation implemented in RTL. Production
source is the implementation reference; link tests separately as validation.
