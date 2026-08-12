#!/usr/bin/env bash
# Archive full-precision base-model weights for reproducibility (roadmap C3/C8 prep).
#
# Prereq (one-time, human): accept the license while logged in as bilalghalib on:
#   https://huggingface.co/google/translategemma-27b-it
#   https://huggingface.co/google/translategemma-12b-it
#   https://huggingface.co/google/translategemma-4b-it
#
# Downloads resume automatically if interrupted. ~110GB total; needs local scratch.
# QE/embedding models are pinned later, during C4/C7 — do not add them here on spec.
set -euo pipefail

DEST="${VERSED_SCRATCH:-/Volumes/Nodes/versed-translator}/models"
MODELS=(
  "google/translategemma-27b-it"
  "google/translategemma-12b-it"
  "google/translategemma-4b-it"
)

mkdir -p "$DEST"
for m in "${MODELS[@]}"; do
  echo "=== $m -> $DEST/${m#google/}"
  hf download "$m" --local-dir "$DEST/${m#google/}"
done

echo
echo "Done. To mirror onto the shared archive (run when convenient):"
echo "  ssh wayway 'mkdir -p /mnt/hikma/versed-translator/models'"
echo "  rsync -avP '$DEST/' wayway:/mnt/hikma/versed-translator/models/"
