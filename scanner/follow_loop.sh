#!/bin/bash
# Run followed-checks of every Best Capper about every 5 minutes for the
# length of the job (FOLLOW_LOOP_SECS). Runs alongside the hourly full scan.
# Each pass that pushes data dispatches deploy.yml so the site updates now,
# not only when the loop ends. If a full scan pushed during a pass, the scan
# wins and this pass is redone from the scan's data on the next cycle.
# Called from .github/workflows/follow-check.yml. Commits data only.
set -euo pipefail
# The workflow runs a copy from $RUNNER_TEMP (each pass resets the checkout to
# the latest main, which may rewrite this file), so FOLLOW_ROOT points at the repo.
ROOT="${FOLLOW_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

git config user.name "kalshi-scanner"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# A queued job may have checked out an older SHA while a scan pushed. Start from latest data.
git pull --rebase origin main || true

CHANGED=0
python3 - <<'PY' || true
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("America/Los_Angeles"))
print("follow-loop start PT %s hour=%d" % (now.strftime("%a %b %-d %-I:%M %p %Z"), now.hour))
PY

END_EPOCH=$(( $(date +%s) + ${FOLLOW_LOOP_SECS:-2880} ))

should_stop() {
  python3 - <<'PY'
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
now_pt = datetime.now(ZoneInfo("America/Los_Angeles"))
if 0 <= now_pt.hour < 6:
    print("quiet hours — stopping the follow loop")
    sys.exit(0)
sys.exit(1)
PY
}

request_deploy() {
  if [ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
    gh workflow run deploy.yml --ref main -R "$GITHUB_REPOSITORY" \
      && echo "requested Pages deploy" \
      || echo "could not dispatch deploy.yml"
  fi
}

sync_main() {
  # Start every pass from the latest pushed data (a full scan may have landed).
  git rebase --abort 2>/dev/null || true
  git fetch -q origin main && git reset -q --hard origin/main
}

run_once() {
  sync_main || true
  export KALSHI_SCAN_MODE=follow
  python scanner/scan.py
  VAL=1
  if [ -f scanner/.follow_changed ]; then
    VAL=$(tr -d '[:space:]' < scanner/.follow_changed)
  fi
  if [ "${VAL:-1}" != "1" ]; then
    echo "No significant follow-check changes."
    return 0
  fi
  python scanner/gate_crypto.py encrypt
  git add data.json
  if [ -d data ]; then git add -A data; fi
  if git diff --cached --quiet; then
    echo "No data changes to commit."
    return 0
  fi
  git commit -m "followed check"
  i=0
  while [ $i -lt 3 ]; do
    i=$((i + 1))
    if git pull --rebase origin main && git push; then
      CHANGED=1
      echo "pushed followed check $(git rev-parse --short HEAD)"
      request_deploy
      return 0
    fi
    echo "push failed (attempt $i)"
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      # data.json conflicted: a full scan landed mid-pass. Keep the scan's
      # data and redo this check from it next cycle.
      echo "full scan landed during this pass; keeping the scan's data"
      sync_main || true
      return 0
    fi
    git rebase --abort 2>/dev/null || true
    sleep 8
  done
  echo "gave up pushing this follow-check"
  return 1
}

# Always do one pass (even if this job started late in the :18–:20 yield
# window), then repeat every 5 minutes until the window ends.
FIRST=1
while true; do
  if [ "$FIRST" != 1 ] && should_stop; then
    break
  fi
  FIRST=0
  START=$(date +%s)
  echo "==== follow-check $(date -u +%H:%M:%SZ) ===="
  run_once || echo "follow-check iteration failed; will try again next cycle"
  NOW=$(date +%s)
  if [ "$NOW" -ge "$END_EPOCH" ]; then
    break
  fi
  SLEEP=$((START + 300 - NOW))
  if [ "$SLEEP" -lt 5 ]; then
    SLEEP=5
  fi
  LEFT=$((END_EPOCH - $(date +%s)))
  if [ "$LEFT" -le 15 ]; then
    break
  fi
  if should_stop; then
    break
  fi
  if [ "$SLEEP" -gt "$LEFT" ]; then
    SLEEP=$LEFT
  fi
  echo "sleeping ${SLEEP}s until the next follow-check"
  sleep "$SLEEP"
done

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  if [ "$CHANGED" = "1" ]; then
    echo "value=1" >> "$GITHUB_OUTPUT"
  else
    echo "value=0" >> "$GITHUB_OUTPUT"
  fi
fi
echo "FOLLOW_LOOP_CHANGED=${CHANGED}"
