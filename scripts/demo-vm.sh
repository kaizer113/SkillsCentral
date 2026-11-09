#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
config_python=${SKILLSCENTRAL_PYTHON:-.venv/bin/python}
exec "$config_python" scripts/demo_vm.py "${@}"
