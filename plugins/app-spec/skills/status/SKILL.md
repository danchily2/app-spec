---
name: status
description: Says where an app-spec run stands for one output folder - which stages are done, what is stale, the coverage per class, the review passes and the Blocker and High findings that remain, and the exact next command. Writes nothing. Use when unsure what to run next for a spec.
argument-hint: "<out>"
---

Report the state of the output folder given in `$ARGUMENTS` (`OUT` below):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status.py" OUT
```

Repeat its lines as they are: one line per stage, the staleness lines, the coverage, the review passes and the
findings that remain, then `Next:` with its reason. Add nothing it does not say, and change no file.

Exit code 2 means `OUT` is not an output folder: say so, and name the command that starts a run,
`/app-spec:spec <app> --module <name> --out OUT`.

## In Devin

- Write the plugin's real folder out instead of `${CLAUDE_PLUGIN_ROOT}`, here and in the `Next:` command
  `status.py` prints. Devin CLI/Desktop gives it in the session-start note. When Devin cloud loads a skill, it prints
  `Base directory: <root>/skills/<skill>`, so the plugin folder is two levels above that. Devin cloud runs no plugin
  hooks; if no base directory was printed, find the installed folder with
  `ls -d ~/.devin/plugins/cache/*app-spec_plugins_app-spec*/*/ 2>/dev/null | sort -V | tail -1`, or use a local
  clone's `plugins/app-spec`. Check that `module.py`'s first output line (`app-spec <version>`) matches the expected
  version.
- This command needs no Workflow tool and asks nothing.

## Finish

Name the exact next command, as `status.py` printed it after `Next:`. When it names a stage that runs inside
`/app-spec:spec` (the understand or rules workflow), the next command is that `/app-spec:spec` line.
