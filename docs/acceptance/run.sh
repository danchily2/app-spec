#!/bin/zsh
# Acceptance run of the installed app-spec plugin in a new headless Claude Code session (handover step 5).
#   zsh docs/acceptance/run.sh <run name, e.g. payslips-v6> [passes, 1 to 5]
# Writes the spec to ~/Documents/GitHub/vmm3/specs/<name> and the session log to
# ~/Documents/GitHub/vmm3/specs/run-logs/<name>.{stream,stderr}.txt.
# CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0: print mode otherwise kills a background workflow 10 minutes after the turn
# ends (v5 attempt 1). --headless: no person answers the scope question; the report says so.
# No --add-dir for the app-spec repo: with it, v5 and v6 ran the scripts from the live working tree (P set to the
# repo path) instead of the installed copy, so edits during a run changed the code under test.
set -u
NAME=${1:?run name, such as payslips-v6}
PASSES=${2:-}
SPECS=~/Documents/GitHub/vmm3/specs
LOGS=$SPECS/run-logs
mkdir -p "$LOGS"
cd ~/Documents/GitHub/vmm3 || exit 1
PROMPT="/app-spec:spec ~/Documents/GitHub/visma-scarlet/sources/me-ios --capabilities ~/Documents/GitHub/visma-scarlet/analysis/work-app/capabilities.json --scope CAP-029,CAP-080,CAP-225,CAP-226,CAP-227,CAP-231 --module Modules/PayslipsFeature --contracts ~/code/me-api --out $SPECS/$NAME --name payslips.md --headless${PASSES:+ --passes $PASSES}

This is an acceptance run of the app-spec plugin. Take every proposal as the skill offers it. Never fix plugin output by hand and never edit the plugin. If the run needs a manual step, stop that step and record it in $SPECS/$NAME/MANUAL_STEPS.md with what was needed and why. End with the Finish report of the skill."
echo "started $(date)" > "$LOGS/$NAME.stderr.txt"
CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 command claude -p "$PROMPT" \
  --permission-mode bypassPermissions --output-format stream-json --verbose \
  --add-dir ~/Documents/GitHub/visma-scarlet --add-dir ~/code/me-api \
  > "$LOGS/$NAME.stream.txt" 2>> "$LOGS/$NAME.stderr.txt"
echo "exit $? at $(date)" >> "$LOGS/$NAME.stderr.txt"
