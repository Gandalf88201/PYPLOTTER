#!/usr/bin/env bash
# π-plotter launcher for macOS and Linux: double-click (macOS) or run ./start_piplotter.command.
# First run: creates a private environment in .venv (standard library only). NumPy, pandas,
# Matplotlib and the optional modules are then installed from the browser page, with a progress bar.
# Extra arguments are passed to start_piplotter.py (e.g. --port 8771). PIPLOTTER_PYTHON picks the Python.
set -euo pipefail
cd "$(dirname "$0")"

fail () {
  echo
  echo "π-plotter: $1"
  [ -t 0 ] && read -r -p "Press Enter to close." _ || true
  exit 1
}

find_python () {
  for candidate in "${PIPLOTTER_PYTHON:-}" python3.13 python3.12 python3.11 python3.10 python3.14 python3 python; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      echo "$candidate"; return 0
    fi
  done
  return 1
}

VENV_PY=.venv/bin/python
if [ ! -x "$VENV_PY" ]; then
  PYTHON=$(find_python) || fail "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/ and run this launcher again."
  echo "Creating the π-plotter environment with $("$PYTHON" --version) …"
  "$PYTHON" -m venv .venv || fail "Could not create .venv (on Debian/Ubuntu install python3-venv)."
fi
# macOS on exFAT/FAT drives: AppleDouble "._*" files confuse some packages; remove them quietly.
if [ "$(uname)" = "Darwin" ] && command -v dot_clean >/dev/null 2>&1; then
  dot_clean -m .venv 2>/dev/null || true
fi

echo "Starting π-plotter — keep this window open; press Ctrl+C to stop."
exec "$VENV_PY" start_piplotter.py "$@"
