#!/usr/bin/env bash
# Deploy the built dashboard to wayway.ai/translator/ and the hikma share.
# Prereqs: `ssh wayway` alias configured; dashboard built via:
#   make -f tools/dashboard.mk dashboard
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASH="$REPO_DIR/docs"
HIKMA_TARGET="/mnt/hikma/versed-translator/dashboard/"

[ -f "$DASH/index.html" ] || { echo "docs/index.html missing — build first" >&2; exit 1; }

# Primary hosting is GitHub Pages (main:/docs) — updates on git push.
# This script refreshes the tailnet copy on hikma via the wayway server.
ssh wayway "mkdir -p $HIKMA_TARGET"
scp -q "$DASH/index.html" "$DASH/status.json" "wayway:$HIKMA_TARGET"

echo "Deployed:"
echo "  https://bilalghalib.github.io/versed_translator/  (updates on git push)"
echo "  /Volumes/hikma/versed-translator/dashboard/index.html (tailnet copy)"
