#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export TEXTFOLD_DATA="${TEXTFOLD_DATA:-$PWD/.web-data}"
export TEXTFOLD_HOME="${TEXTFOLD_HOME:-$PWD/.web-settings}"
exec "${TEXTFOLD_PYTHON:-.venv/bin/python}" -m textfold account "$@"
