#!/usr/bin/env bash
# run_daily.sh - Daily execution wrapper for Sonar
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 仮想環境のPython
PYTHON="$SCRIPT_DIR/.venv/bin/python"

# .env があれば環境変数を読み込む
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

echo "=== Starting Sonar at $(date -u) ==="
PYTHONPATH="$SCRIPT_DIR" "$PYTHON" -m src.cli run

echo "=== Updating Static Site ==="
"$PYTHON" "$SCRIPT_DIR/build_site.py"

echo "=== Finished Sonar at $(date -u) ==="
