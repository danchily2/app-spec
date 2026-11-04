---
name: start
description: Starts an app-spec spec run (/app-spec:spec) when a person explicitly asks for one in a session that cannot type the slash command, such as Devin cloud. Never start a run unprompted - one costs about an hour and a half of agent time.
---

A person asked for an app-spec spec run: `$ARGUMENTS` (or their message) names the app, the module and the output
folder, in the form `<app> --module <name> --out <folder>` with the options of `/app-spec:spec`.

1. In Claude Code, say "Type `/app-spec:spec <app> --module <name> --out <folder>`" and stop: there the command
   itself is the entry point.
2. Otherwise the plugin folder is two levels above this skill's base directory (`<base>/../..`). Read
   `<plugin folder>/skills/spec/SKILL.md` and follow it from the top, with the person's words as its `$ARGUMENTS`
   and that folder as `${CLAUDE_PLUGIN_ROOT}`.
3. If the person did not name an app, a module and an output folder, ask for the missing ones in one question before
   step 1 of the spec skill.
