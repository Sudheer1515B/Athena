#!/bin/zsh
set -e

PROJECT_ROOT="${0:A:h}"
if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  echo "Athena's .venv is missing. See PROTOTYPE_DEMO.md for setup."
  read -r "?Press Enter to close..."
  exit 1
fi

cd "$PROJECT_ROOT"
exec "$PROJECT_ROOT/.venv/bin/python" scripts/demo_launcher.py hardware "$@"
