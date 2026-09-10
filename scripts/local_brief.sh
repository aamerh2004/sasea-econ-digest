#!/bin/bash
# Generates the daily AI brief locally using the Claude Code CLI signed in to
# your Claude subscription (no API key, no billing), then publishes it.
#
# GitHub Actions builds the articles each morning; this adds the brief on top.
# Run daily by launchd, which fires missed jobs when the Mac wakes.
set -uo pipefail

REPO="/Users/aamerhusain/Projects/sasea-econ-digest"
CLAUDE="/Users/aamerhusain/Library/Application Support/Claude/claude-code/2.1.260/claude.app/Contents/MacOS/claude"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "$REPO" || exit 1
LOG="$REPO/data/brief-run.log"
echo "=== $(date '+%Y-%m-%d %H:%M:%S') starting ===" >> "$LOG"

# Take whatever GitHub Actions already published this morning.
git pull --rebase --quiet >> "$LOG" 2>&1 || {
  echo "git pull failed, continuing with local state" >> "$LOG"
}

DIGEST_PATH=$(ls -1 data/digests/*.json 2>/dev/null | tail -1)
if [ -z "$DIGEST_PATH" ]; then
  echo "no digest found, nothing to summarize" >> "$LOG"
  exit 0
fi
DATE=$(basename "$DIGEST_PATH" .json)

if [ -s "data/briefs/$DATE.json" ]; then
  echo "brief for $DATE already exists, nothing to do" >> "$LOG"
  exit 0
fi

mkdir -p data/briefs

PROMPT="$(cat scripts/brief_prompt.md)

The digest to summarize is data/digests/$DATE.json.
Write your brief to data/briefs/$DATE.json.
Write only that one file. Do not commit or push."

echo "generating brief for $DATE" >> "$LOG"
"$CLAUDE" -p "$PROMPT" \
  --allowedTools "Read,Write" \
  --permission-mode acceptEdits >> "$LOG" 2>&1

if [ ! -s "data/briefs/$DATE.json" ]; then
  echo "brief was not produced; leaving site as-is" >> "$LOG"
  exit 1
fi

if ! python3 -c "import json,sys; json.load(open('data/briefs/$DATE.json'))" 2>>"$LOG"; then
  echo "brief is not valid JSON; discarding it" >> "$LOG"
  rm -f "data/briefs/$DATE.json"
  exit 1
fi

# Render with the project's own venv so dependencies are present.
if [ -x "$REPO/venv/bin/python" ]; then
  "$REPO/venv/bin/python" scripts/render_site.py >> "$LOG" 2>&1
else
  python3 scripts/render_site.py >> "$LOG" 2>&1
fi

git add data/briefs docs >> "$LOG" 2>&1
if git diff --staged --quiet; then
  echo "nothing changed" >> "$LOG"
  exit 0
fi

git -c user.name="sasea-digest-bot" \
    -c user.email="actions@users.noreply.github.com" \
    commit -q -m "Daily brief $DATE" >> "$LOG" 2>&1
if git push --quiet >> "$LOG" 2>&1; then
  echo "published brief for $DATE" >> "$LOG"
else
  # Most likely the morning's Actions run landed first; rebase onto it and retry.
  echo "push rejected, rebasing onto origin and retrying" >> "$LOG"
  if git pull --rebase --quiet >> "$LOG" 2>&1 && git push --quiet >> "$LOG" 2>&1; then
    echo "published brief for $DATE after rebase" >> "$LOG"
  else
    echo "push still failing; brief is committed locally only" >> "$LOG"
  fi
fi
