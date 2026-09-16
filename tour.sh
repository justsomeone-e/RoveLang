#!/usr/bin/env bash
set -e

# Tour of Nyx Unix / macOS Launcher
if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
else
    echo "[ERROR] Python 3.10+ is required to launch Tour of Nyx."
    echo "Please install Python from your package manager or https://www.python.org/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -eq 0 ]; then
    exec "$PY_CMD" "$SCRIPT_DIR/tour/tour.py" core
else
    exec "$PY_CMD" "$SCRIPT_DIR/tour/tour.py" "$@"
fi
