#!/usr/bin/env bash
# 15-minute harvest tick loop. Writes to log and stdout for Cursor notify_on_output.
# Sleep in 60s chunks so macOS/App Nap kills are less likely; heartbeat proves liveness.
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="${HARVEST_LOOP_LOG:-$HOME/versed-translator-data/harvest_loop.log}"
PIDFILE="${HARVEST_LOOP_PID:-$HOME/versed-translator-data/harvest_loop.pid}"
INTERVAL="${HARVEST_LOOP_INTERVAL:-900}"
HEARTBEAT_EVERY="${HARVEST_LOOP_HEARTBEAT:-300}"
PROMPT='Continue the English corpus harvest: one host-first pass (~15 min). Checkout feat/corpus-harvest until PR #8 merges. Read corpus/harvest_log.json do_next, person_pages_todo, and do_not. Strategy: walk ONE unexhausted al-islam person/translator page; batch every OpenITI match via cover-image slugs to printpdf (crawl-delay 10). Do NOT pick random inventory gaps (low yield). Never mix train-english into pd-english. Never invent OpenITI URIs. Catalog keepers, append harvest_log, reload inventory. Commit to feat/corpus-harvest and push.'

mkdir -p "$(dirname "$LOG")"

if [[ -f "$PIDFILE" ]]; then
  old_pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop already running pid=$old_pid" >> "$LOG"
    exit 0
  fi
fi

echo "$$" > "$PIDFILE"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop started pid=$$ interval=${INTERVAL}s heartbeat=${HEARTBEAT_EVERY}s" >> "$LOG"
trap 'echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop exit pid=$$ code=$?" >> "$LOG"; rm -f "$PIDFILE"' EXIT

sleep_interval() {
  local total="$1" elapsed=0 since_hb=0
  while (( elapsed < total )); do
    sleep 60 || return 1
    elapsed=$((elapsed + 60))
    since_hb=$((since_hb + 60))
    if (( since_hb >= HEARTBEAT_EVERY )); then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) harvest_loop heartbeat pid=$$ elapsed=${elapsed}s/${total}s" >> "$LOG"
      since_hb=0
    fi
  done
}

while true; do
  sleep_interval "$INTERVAL"
  TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  LINE="AGENT_LOOP_TICK_harvest {\"prompt\":\"$PROMPT\"}"
  echo "$TS $LINE" >> "$LOG"
  echo "$LINE"
done
