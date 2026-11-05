#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

TEXTFOLD_PYTHON="${TEXTFOLD_PYTHON:-.venv/bin/python}"
if [[ ! -x "$TEXTFOLD_PYTHON" ]]; then
  echo "请先安装网页运行环境，见 docs/WEB.md。"
  exit 1
fi
export TEXTFOLD_DATA="${TEXTFOLD_DATA:-$PWD/.web-data}"
export TEXTFOLD_HOME="${TEXTFOLD_HOME:-$PWD/.web-settings}"
exec "$TEXTFOLD_PYTHON" -u -m textfold serve --web --auth --host "${TEXTFOLD_BIND_HOST:-127.0.0.1}" --port "${PORT:-3017}"
