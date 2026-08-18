#!/usr/bin/env bash
# 15-minute harvest tick loop. Writes to log and stdout for Cursor notify_on_output.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="${HARVEST_LOOP_LOG:-$HOME/versed-translator-data/harvest_loop.log}"
PIDFILE="${HARVEST_LOOP_PID:-$HOME/versed-translator-data/harvest_loop.pid}"
INTERVAL="${HARVEST_LOOP_INTERVAL:-900}"
PROMPT='Continue the English corpus harvest: one host-first pass (~15 min). Checkout feat/corpus-harvest until PR #8 merges. Read corpus/harvest_log.json do_next and do_not. Search for a live slug first, then book page to printpdf with crawl-delay 10. Never mix train-english into pd-english. Never invent OpenITI URIs. Never re-run DEEP_QUERIES or leftover IA aliases. Never re-scrape Ansariyan, World Federation, WOFIS, or Islamic Seminary grids. Catalog keepers, append harvest_log, reload inventory. If zero keepers, log why. Commit to feat/corpus-harvest and push.'

mkdir -p "$(dirname "$LOG")"
echo "$$" > "$PIDFILE"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop started pid=$$ interval=${INTERVAL}s" >> "$LOG"
trap 'echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop exit pid=$$ code=$?" >> "$LOG"' EXIT

while true; do
  sleep "$INTERVAL" || exit 1
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  LINE="AGENT_LOOP_TICK_harvest {\"prompt\":\"$PROMPT\"}"
  echo "$TS $LINE" >> "$LOG"
  echo "$LINE"
done
