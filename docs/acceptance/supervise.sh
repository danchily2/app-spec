#!/bin/zsh
# Keep an acceptance run going across usage-limit stops.
#   zsh docs/acceptance/supervise.sh <run name, e.g. payslips-v7b> [max resumes, default 4]
# Waits while the run's headless session is alive. When the session stopped with usage_limit_reached, it waits until
# the reset time the log reports (plus 5 minutes) and resumes the same session with `claude -p --resume`. Any other
# end (finished, another error) stops the supervisor. Each resume appends to <name>.stream.txt.
set -u
NAME=${1:?run name}
MAX=${2:-4}
LOGS=~/Documents/GitHub/vmm3/specs/run-logs
STREAM=$LOGS/$NAME.stream.txt
ERR=$LOGS/$NAME.stderr.txt
note() { echo "supervise: $* ($(date))" >> "$ERR"; }

alive() { pgrep -f "claude -p .*specs/$NAME " > /dev/null 2>&1 || pgrep -f "claude -p --resume $SID" > /dev/null 2>&1; }

SID=$(grep -o '"session_id":"[^"]*"' "$STREAM" | head -1 | cut -d'"' -f4)
[[ -n "$SID" ]] || { note "no session id in $STREAM"; exit 1; }
n=0
while true; do
  while alive; do sleep 60; done
  last=$(grep '"type":"result"' "$STREAM" | tail -1)
  if [[ "$last" != *usage_limit_reached* ]]; then
    note "the run ended without a usage-limit stop; done"
    exit 0
  fi
  (( n >= MAX )) && { note "stopped by the usage limit $n times; giving up"; exit 2; }
  reset=$(grep -o '"resetsAt":[0-9]*' "$STREAM" | tail -1 | cut -d: -f2)
  now=$(date +%s)
  wait=$(( ${reset:-$(( now + 3600 ))} - now + 300 ))
  (( wait < 300 )) && wait=300
  note "usage limit; resume $((n + 1)) of $MAX in $(( wait / 60 )) min"
  sleep $wait
  n=$(( n + 1 ))
  cd ~/Documents/GitHub/vmm3 || exit 1
  CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 command claude -p --resume "$SID" \
    "The usage limit stopped this acceptance run. Continue the /app-spec:spec run exactly where it stopped: resume any stopped workflow with its Run ID (resumeFromRunId), never restart a step that finished, and keep every rule of the first prompt. End with the Finish report of the skill." \
    --permission-mode bypassPermissions --output-format stream-json --verbose \
    --add-dir ~/Documents/GitHub/visma-scarlet --add-dir ~/code/me-api \
    >> "$STREAM" 2>> "$ERR" &
  sleep 30
done
