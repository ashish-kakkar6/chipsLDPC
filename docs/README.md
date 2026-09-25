# Documentation

The site uses Sphinx and MyST Markdown.

From the repository root:

```sh
python3 -m venv .venv-docs
./.venv-docs/bin/python -m pip install -r requirements-docs.txt
make -C docs html PYTHON="$(pwd)/.venv-docs/bin/python"
```

Open `docs/_build/html/index.html` after the build completes.
