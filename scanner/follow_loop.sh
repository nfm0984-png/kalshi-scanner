#!/bin/bash
# Run followed-checks of every Best Capper about every 5 minutes until just
# before the :20 UTC full scan, then stop so scanner.yml can start on time.
# Called from .github/workflows/follow-check.yml. Commits data only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
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
utc = datetime.now(timezone.utc)
# Yield just before the :20 UTC hourly full scan. A delayed loop that
# starts at :21–:24 (after that scan should have begun) still does a pass.
if 18 <= utc.minute <= 20:
    print("near :20 UTC — stopping so the full scan can run")
    sys.exit(0)
sys.exit(1)
PY
}

run_once() {
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
      return 0
    fi
    echo "push failed (attempt $i); retrying"
    # data.json often conflicts; keep this run's data ("theirs" during rebase).
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      git checkout --theirs -- data.json data 2>/dev/null || true
      git add data.json
      if [ -d data ]; then git add -A data; fi
      if GIT_EDITOR=true git rebase --continue && git push; then
        CHANGED=1
        echo "pushed followed check $(git rev-parse --short HEAD)"
        return 0
      fi
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
