#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$SCRIPT_DIR/../.isai/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "ISAI virtual environment not found at $VENV_PY" >&2
  exit 1
fi
cd "$SCRIPT_DIR"
exec "$VENV_PY" main.py "$@"
