#!/bin/sh
# app-spec source write guard. The real check is scripts/guard.py, which finds the output folder(s) (app-spec.json) from
# the project folder, the shell's folder and the paths the tool call names, above and two levels below, and does
# nothing outside one. It runs on every matched tool call (about 30 ms); a cheaper gate here would have to repeat that
# discovery, and a gate that only looked at the project folder would skip cases the script catches.
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "${CLAUDE_PLUGIN_ROOT:-${DEVIN_PLUGIN_ROOT:-$(dirname "$0")/..}}/scripts/guard.py"
