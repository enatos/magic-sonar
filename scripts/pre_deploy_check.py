#!/usr/bin/env python3
"""
pre_deploy_check.py - Security inspection before deploying to Cloudflare Pages
Checks for secrets, internal URLs, GATE tokens, and personal info in dist/
"""

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"

if not DIST_DIR.exists():
    print(f"Error: {DIST_DIR} does not exist. Run build_site.py first.", file=sys.stderr)
    sys.exit(1)

dist_files = list(DIST_DIR.glob("*.*"))
if not dist_files:
    print(f"Error: No files found in {DIST_DIR}. Run build_site.py first.", file=sys.stderr)
    sys.exit(1)

content_parts = []
for f in dist_files:
    if f.suffix in [".html", ".json", ".md", ".txt"]:
        content_parts.append(f.read_text(encoding="utf-8"))

content = "\n".join(content_parts)

checks = [
    ("GATE-api or polaris keywords", re.findall(r"(?:gate-api|polaris|pol_[a-zA-Z0-9_-]+)", content, re.IGNORECASE)),
    (".secrets reference", re.findall(r"\.secrets", content, re.IGNORECASE)),
    ("User local absolute path (/Users/)", re.findall(r"/Users/[a-zA-Z0-9_-]+", content)),
    ("GitHub Personal Access Token", re.findall(r"(?:ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})", content)),
    ("Cloudflare Token / Secrets", re.findall(r"(?:CLOUDFLARE_[A-Z_]+|CF_API_[A-Z_]+)", content)),
    ("Notion API Token", re.findall(r"(?:secret_[a-zA-Z0-9]{43}|ntn_[a-zA-Z0-9_]+)", content)),
    ("Private IPs / Localhost URLs", re.findall(r"(?:127\.0\.0\.1|localhost:\d+)", content)),
]

print("=== Pre-Deployment Security Check ===")
has_violation = False
for name, matches in checks:
    if matches:
        print(f"[FAIL] {name}: Found {len(matches)} matches -> {set(matches)}")
        has_violation = True
    else:
        print(f"[PASS] {name}: Clean")

if has_violation:
    print("\nResult: SECURITY CHECK FAILED", file=sys.stderr)
    sys.exit(1)
else:
    print("\nResult: ALL SECURITY CHECKS PASSED!")
    sys.exit(0)
