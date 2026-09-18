#!/usr/bin/env bash
# deploy.sh - Build and deploy Sonar static page to Cloudflare Pages
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

echo "=== 1. Building static site from data/sonar.jsonl ==="
"$PYTHON" "$SCRIPT_DIR/build_site.py"

echo "=== 2. Running Pre-deployment Security Check ==="
"$PYTHON" "$SCRIPT_DIR/scripts/pre_deploy_check.py"

echo "=== 3. Deploying to Cloudflare Pages (project: sonar) ==="
npx wrangler pages deploy "$SCRIPT_DIR/dist" --project-name sonar --commit-dirty=true
