#!/usr/bin/env bash
# 15-minute harvest tick loop. Writes to log and stdout for Cursor notify_on_output.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="${HARVEST_LOOP_LOG:-$HOME/versed-translator-data/harvest_loop.log}"
PIDFILE="${HARVEST_LOOP_PID:-$HOME/versed-translator-data/harvest_loop.pid}"
INTERVAL="${HARVEST_LOOP_INTERVAL:-900}"
PROMPT='Continue the English corpus harvest: one host-first pass (~15 min). Checkout feat/corpus-harvest until PR #8 merges. Read corpus/harvest_log.json do_next, person_pages_todo, and do_not. Strategy: walk ONE unexhausted al-islam person/translator page; batch every OpenITI match via cover-image slugs to printpdf (crawl-delay 10). Do NOT pick random inventory gaps (low yield). Never mix train-english into pd-english. Never invent OpenITI URIs. Catalog keepers, append harvest_log, reload inventory. Commit to feat/corpus-harvest and push.'

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
