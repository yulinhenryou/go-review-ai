#!/bin/sh
set -eu

python_bin=${PYTHON:-.venv/bin/python}

RUN_KATAGO_INTEGRATION=1 "$python_bin" -m pytest -q -ra
node --test tests/frontend/*.test.mjs
"$python_bin" -m pip check
git diff --check
