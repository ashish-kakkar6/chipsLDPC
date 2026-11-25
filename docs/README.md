# Documentation

The site uses Sphinx and MyST Markdown. From the repository root:

```sh
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs.txt
make -C docs html PYTHON="$(pwd)/.venv-docs/bin/python"
```

Open `docs/_build/html/index.html`. The build treats warnings as errors and checks
committed figure and learning assets. Ordinary builds do not run simulations,
render Manim, or need the source presentation.

## Editing

Keep executable instructions in the user guides. Example READMEs link to those
guides. Scientific definitions and implementation details belong in the model
and architecture references. Explain the experiment before linking source code.

```sh
make -C docs check-assets
make -C docs html PYTHON="$(pwd)/.venv-docs/bin/python"
make -C docs linkcheck PYTHON="$(pwd)/.venv-docs/bin/python"
```

External link checking requires network access. Check the first-run commands on
a fresh output directory and check resume after a completed run. Inspect the
landing page, video controls/captions, result plots, and tables on narrow screens.

## Figures and learning material

```sh
python3 docs/figures/build_tanner.py
python3 docs/figures/build_architecture.py
./chipsldpc results check
./chipsldpc results plot --out runs/archived-figures
python3 docs/learning_assets.py --check
```

The frozen BB144 bundle retains its original data identity. Add new results under
another versioned directory. The learning bundle includes the captured Steane
animation, captions, transcript, full reference traces, teaching fixtures, and a QEC-only PDF excerpt. Its
manifest records asset hashes, source provenance, and the selected PDF pages.
See `docs/learning_assets.py --help` for controlled republication from the source
projects. Preserve the source talk and animation project.

The animation's eight numerical steps and four final outcomes can be replayed
against the current integer reference with
`./mill --no-server chipsLDPC.test.testOnly chipsldpc.AnimationTraceSpec`.

Repository-relative source links render as highlighted source pages. Use a
verified `#L<number>` anchor when a particular line is useful. The extension
checks file/line existence; review the symbol after code changes.
