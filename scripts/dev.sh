#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  cat <<'EOF'
Project virtualenv is missing.
Create it with:
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt
EOF
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
  cat <<'EOF'
Project virtualenv is not using Python 3.12+.
Recreate it with:
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt
EOF
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import uvicorn' >/dev/null 2>&1; then
  cat <<'EOF'
Project virtualenv is missing dependencies.
Install them with:
  .venv/bin/pip install -r requirements.txt
EOF
  exit 1
fi

exec "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
