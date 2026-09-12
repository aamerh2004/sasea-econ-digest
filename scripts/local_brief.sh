#!/bin/bash
# Generates the daily AI brief locally using the Claude Code CLI signed in to
# your Claude subscription (no API key, no billing), then publishes it.
#
# GitHub Actions builds the articles each morning at 11:00 UTC (7am EDT);
# this runs afterwards and adds the brief on top. Run daily by launchd, which
# fires missed jobs when the Mac wakes.
set -uo pipefail

REPO="/Users/aamerhusain/Projects/sasea-econ-digest"
CLAUDE="/Users/aamerhusain/Library/Application Support/Claude/claude-code/2.1.260/claude.app/Contents/MacOS/claude"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# How many recent days to backfill if briefs were missed (machine off, etc).
BACKFILL_DAYS=3

cd "$REPO" || exit 1
LOG="$REPO/data/brief-run.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

log "=== starting ==="

# A dirty tree blocks the rebase, and the failure looks identical to a
# network error in the log, so call it out separately.
if ! git diff --quiet || ! git diff --cached --quiet; then
  log "NOTE: working tree has uncommitted changes; git pull --rebase will fail"
fi

# After a wake the network often isn't up yet, so retry before giving up.
# Proceeding on a failed pull would mean summarizing a stale digest.
pulled=0
for attempt in 1 2 3 4 5; do
  if git pull --rebase --quiet >> "$LOG" 2>&1; then
    pulled=1
    break
  fi
  log "pull attempt $attempt failed, retrying in 30s"
  sleep 30
done
if [ "$pulled" -ne 1 ]; then
  log "ABORT: could not pull from origin; refusing to work from stale state"
  exit 1
fi

mkdir -p data/briefs

# Generate for any recent digest that has no brief yet, oldest first, so a
# missed day is filled in rather than silently skipped forever.
pending=$(ls -1 data/digests/*.json 2>/dev/null | tail -"$BACKFILL_DAYS")
generated=0

for digest_path in $pending; do
  date_str=$(basename "$digest_path" .json)
  if [ -s "data/briefs/$date_str.json" ]; then
    continue
  fi

  log "generating brief for $date_str"
  PROMPT="$(cat scripts/brief_prompt.md)

The digest to summarize is data/digests/$date_str.json.
Write your brief to data/briefs/$date_str.json.
Write only that one file. Do not commit or push."

  "$CLAUDE" -p "$PROMPT" \
    --allowedTools "Read,Write" \
    --permission-mode acceptEdits >> "$LOG" 2>&1

  if [ ! -s "data/briefs/$date_str.json" ]; then
    log "WARNING: no brief produced for $date_str"
    continue
  fi
  if ! python3 -c "import json;json.load(open('data/briefs/$date_str.json'))" 2>>"$LOG"; then
    log "WARNING: brief for $date_str was not valid JSON; discarding"
    rm -f "data/briefs/$date_str.json"
    continue
  fi
  log "brief for $date_str written"
  generated=$((generated + 1))
done

if [ "$generated" -eq 0 ]; then
  log "no new briefs needed"
  exit 0
fi

if [ -x "$REPO/venv/bin/python" ]; then
  "$REPO/venv/bin/python" scripts/render_site.py >> "$LOG" 2>&1
else
  python3 scripts/render_site.py >> "$LOG" 2>&1
fi

git add data/briefs docs >> "$LOG" 2>&1
if git diff --staged --quiet; then
  log "nothing to commit"
  exit 0
fi

git -c user.name="sasea-digest-bot" \
    -c user.email="actions@users.noreply.github.com" \
    commit -q -m "Daily brief ($generated day(s))" >> "$LOG" 2>&1

if git push --quiet >> "$LOG" 2>&1; then
  log "published $generated brief(s)"
else
  log "push rejected, rebasing onto origin and retrying"
  if git pull --rebase --quiet >> "$LOG" 2>&1 && git push --quiet >> "$LOG" 2>&1; then
    log "published $generated brief(s) after rebase"
  else
    log "ERROR: push failed; briefs are committed locally only"
    exit 1
  fi
fi
