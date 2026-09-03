#!/usr/bin/env bash
# Create the repository-local Python environment for the BB144 experiment.
set -euo pipefail
python3 -m venv .venv
exec .venv/bin/python -m pip install -r examples/BivariateBicycle144/requirements.txt
