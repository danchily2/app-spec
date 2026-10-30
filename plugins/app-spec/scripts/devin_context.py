#!/usr/bin/env python3
"""SessionStart hook, Devin only: how to read app-spec's skills and agents, which were written for Claude Code.

Prints a hookSpecificOutput.additionalContext with the plugin's real folder (for ${CLAUDE_PLUGIN_ROOT}, which Devin
does not expand inside a skill), the Devin names of the tools the skills mention, the path to take without the
Workflow tool, and the defaults of the plugin options Devin does not have. Prints nothing outside Devin (neither
DEVIN_PLUGIN_ROOT nor DEVIN_PROJECT_DIR set). Standard library only.
"""

import json
import os

ROOT = os.path.realpath(os.environ.get("DEVIN_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
                        or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTEXT = """\
The app-spec plugin is installed at <root>. Its skills (/app-spec:*) and agents were written for Claude Code; \
when you run one in Devin, read it this way:
- `${CLAUDE_PLUGIN_ROOT}` is <root>. Your shell does not set it: write that path out in every command.
- AskUserQuestion is ask_user_question, with the same limits (1-4 questions, 2-4 options each; multiSelect is \
multi_select).
- There is no Workflow tool: take each skill's "Without the Workflow tool" path, with run_subagent and the plugin's \
profiles app-spec:<agent> (for example app-spec:ios-analyst). One foreground subagent runs at a time; to run \
several in parallel start them in the background and wait for each with read_subagent (block=true). Background \
subagents only get tools already approved in this session.
- Bash is exec (a long command returns a shell_id: read it with get_output); Read, Write, Edit, Grep and Glob are \
read, write, edit, grep and glob.
- Devin has no plugin options: the review passes default is 2 unless the person names another number, and \
APP_SPEC_GUARD=false in Devin's environment turns the source write guard off.
- Devin reads permission deny rules from .devin/config.json, not .claude/settings.json: when a skill prints deny rules \
for the analysed app and the contract repositories, put them in .devin/config.json.
"""


def main():
    if not (os.environ.get("DEVIN_PLUGIN_ROOT") or os.environ.get("DEVIN_PROJECT_DIR")):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": CONTEXT.replace("<root>", ROOT)}}))


if __name__ == "__main__":
    main()
