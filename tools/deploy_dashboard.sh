#!/usr/bin/env bash
# Deploy the built dashboard to wayway.ai/translator/ and the hikma share.
# Prereqs: `ssh wayway` alias configured; dashboard built via:
#   make -f tools/dashboard.mk dashboard
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DASH="$REPO_DIR/dashboard"
WEB_DIR="/home/bilal/public_html/versed/translator"
HIKMA_TARGET="/mnt/hikma/versed-translator/dashboard/"

[ -f "$DASH/index.html" ] || { echo "dashboard/index.html missing — build first" >&2; exit 1; }

ssh wayway "mkdir -p $WEB_DIR"
scp -q "$DASH/index.html" "$DASH/status.json" "wayway:$WEB_DIR/"
ssh wayway "chown -R bilal:bilal $WEB_DIR && mkdir -p $HIKMA_TARGET && cp $WEB_DIR/index.html $WEB_DIR/status.json $HIKMA_TARGET"

echo "Deployed:"
echo "  https://versed.wayway.ai/translator/"
echo "  /Volumes/hikma/versed-translator/dashboard/index.html (tailnet copy)"
