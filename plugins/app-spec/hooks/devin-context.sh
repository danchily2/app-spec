#!/bin/sh
# app-spec under Devin. Devin loads this plugin in its Claude Code layout, but does not expand ${CLAUDE_PLUGIN_ROOT}
# inside a skill, has no Workflow tool and names its tools differently. At session start scripts/devin_context.py
# prints that mapping, with the plugin's real folder, as context. Under Claude Code (which sets neither
# DEVIN_PLUGIN_ROOT nor DEVIN_PROJECT_DIR) it prints nothing.
[ -n "$DEVIN_PLUGIN_ROOT$DEVIN_PROJECT_DIR" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "${DEVIN_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-$(dirname "$0")/..}}/scripts/devin_context.py"
