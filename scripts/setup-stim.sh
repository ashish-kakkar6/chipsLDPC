#!/usr/bin/env bash
# Create the repository-local Python environment used by Stim examples.
set -euo pipefail
python3 -m venv .venv
exec .venv/bin/python -m pip install -r examples/RotatedSurfaceCode/requirements.txt
