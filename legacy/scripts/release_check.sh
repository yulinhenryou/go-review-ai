#!/bin/sh
set -eu

python_bin=${PYTHON:-.venv/bin/python}

"$python_bin" scripts/test_python.py
node --test tests/frontend/*.test.mjs
"$python_bin" -m pip check
git diff --check
