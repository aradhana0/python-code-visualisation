#!/usr/bin/env bash
# Installs (or updates) a cron schedule that runs the job tracker every morning and evening.
# Usage: scripts/install_cron.sh [MORNING_HH:MM] [EVENING_HH:MM]   (local time, default 08:52 and 18:52)
#        scripts/install_cron.sh --remove
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
MARK="# job-tracker"

current="$(crontab -l 2>/dev/null | grep -v "$MARK" || true)"
if [[ "${1:-}" == "--remove" ]]; then
  printf '%s\n' "$current" | crontab -
  echo "Removed job-tracker schedule."
  exit 0
fi

[[ -f "$REPO/profile.toml" ]] || { echo "Create $REPO/profile.toml first (see profile.example.toml)."; exit 1; }

morning="${1:-08:52}"; evening="${2:-18:52}"
entry() {  # $1 = HH:MM
  local h="${1%%:*}" m="${1##*:}"
  echo "$((10#$m)) $((10#$h)) * * * cd \"$REPO\" && \"$PYTHON\" -m job_tracker run --pdf >> \"$REPO/output/cron.log\" 2>&1 $MARK"
}
mkdir -p "$REPO/output"
{ [[ -n "$current" ]] && printf '%s\n' "$current"; entry "$morning"; entry "$evening"; } | crontab -
echo "Scheduled job tracker at $morning and $evening daily (local time). Log: $REPO/output/cron.log"
crontab -l | grep "$MARK"
