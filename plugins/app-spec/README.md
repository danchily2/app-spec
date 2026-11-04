# App Spec

Point Claude at one module of one mobile app and get a reviewed spec of it. The app can be native iOS, React Native or
native Android. The spec follows a fixed template and is deep enough to plan and build the same feature in a new app
without reading the old code again. You get:
- the module's **use cases, screens, flows, endpoints and business rules**, each with an id and a `file:line` citation
- **numbered acceptance criteria**, each one observable on screen, so a UI test or a unit test can assert it
- a **coverage ledger**: every screen, endpoint, analytics event, permission, storage key, string and field the module
  holds, counted, with a reason for each one left out
- a **critic's review** of the draft, with the findings that remain, and the **open questions** only a person can answer
- a spec that **never reproduces a secret**, and an analysed app that is **never written to**

## Install

You need [Claude Code](https://code.claude.com). In a session:

```
/plugin marketplace add danchily2/app-spec
/plugin install app-spec@app-spec
```

From a local clone, without installing:

```
claude --plugin-dir plugins/app-spec
```

It runs in Devin (the CLI and Devin Desktop) too, which loads the same Claude Code layout:

```
devin plugins install danchily2/app-spec#plugins/app-spec      # or --local /path/to/app-spec/plugins/app-spec
```

The commands are the same (`/app-spec:spec` and so on). See *Devin differences* below.

The full spec run starts many agents, one per slice of the module and one per use case, so expect real usage on a large
module (see *What to expect*).

## Start here

Open a folder for the work, next to the app or anywhere else, and type:

```
/app-spec:spec ~/code/my-ios-app --module Payslips --out ./specs/payslips
```

`--module` is a folder name, a folder or a glob inside the app. Repeat it for several folders. `--out` is the output
folder: it must be outside the app, and it is the only place the plugin writes. The command:
1. finds the module's folders, the files outside them that it needs, and the string keys it shows
2. shows you that scope and asks one question, "Is this the module?"
3. runs the steps in *The path* below
4. ends on the exact next command

Useful options: `--contracts <backend repo>` reads each endpoint's contract from a backend repository, `--bar <file>`
gives the critic a spec you wrote by hand as the bar, `--passes N` sets the most review rounds (1 to 5, default 2), and
`--headless` asks nothing and takes every proposal. `/app-spec:status ./specs/payslips` says where you are and what to
run next, at any time.

**Nothing edits your app.** The commands write only to the output folder. A hook denies file writes into the app and
into each backend repository you gave.

## The path

| Step | What runs | What it writes |
| --- | --- | --- |
| 1 | Scope: `module.py` | `app-spec.json`, `module.json`, one file per shard. You confirm the module here. |
| 2 | Inventory: `inventory.py` | `inventory.json` and `INVENTORY.md`: every screen, endpoint, event, permission, storage key, string and field in the module, each count with the rule that made it. Plus `fields.json`. |
| 3 | Use cases, screens and flows | `understand_result.json`. One analyst per slice of the code, one mapper, and one referee per use case that re-checks its citations. |
| 4 | Business rules | `rules_result.json`. One extractor per slice, one referee per rule, and two judges per P0 rule. |
| 5 | Endpoint contracts | `endpoints.json` with request and response fields, errors and auth. With a backend repository, each route is found there and the two sides are compared. |
| 6 | Catalogs: `render.py catalogs` | `use-cases.json`, `screens.json`, `flows.json`, `rules.json`, `endpoints.json`, and `ids.json`, which keeps every id stable. |
| 7 | Write | `prose.json`: the spec writer's text, from the catalogs and the cited code only. |
| 8 | Review loop | `SPEC.md`, `LEDGER.md`, `grade.json`, `REVIEW.md`: render, count, grade, critic, fix, up to the configured passes. |
| 9 | Open questions | `OPEN_QUESTIONS.md`, each question with what was searched and who can answer. |

`/app-spec:review <out>` runs the count, the grader and the critic again on a spec a person has edited. It changes
nothing in the spec. `/app-spec:review <out> --accept` offers each uncovered item and records the reason you give in
`overrides.json`.

The spec has eight sections: Summary, Capabilities, Screens, Endpoints, Business rules and permissions, Acceptance
criteria, Dependencies and decisions, Open questions. Six appendices follow: fields and ids, data, behaviour to keep and
implementation to drop, strings and analytics and platform, flows, coverage. Every claim carries an evidence label:
`VERIFIED`, `INFERRED`, `UNKNOWN` or `PROPOSED`.

**A person decides at these points, never the plugin:**
- whether the proposed scope is the module
- the reason for every item left out of the spec
- every open question, and every rule the plugin marked with low confidence
- every correction, recorded in `overrides.json`, which the plugin never overwrites

## How completeness and depth are measured

A spec can look complete and still miss the endpoint that a rarely used screen calls. So the measure does not come from
a model's opinion alone:

1. **The inventory is deterministic.** A script counts what the module holds, with a stated rule for each count. A
   model never decides what exists.
2. **The ledger compares the spec to the inventory.** Each class has a threshold: 100 percent for screens, endpoints,
   events, permissions and storage keys, 95 percent for strings and fields. An item counts as covered when a catalog
   entry cites it, or when it is left out for a recorded reason. An uncovered item without a reason counts against its
   class. The thresholds are set in `app-spec.json`.
3. **The grader checks the shape.** Ten checks cover the section order, rules and acceptance criteria for every use
   case, AC numbering, citations that resolve to a real line, an owner and a search note for every `UNKNOWN`, no
   leftover placeholder, no duplicate use case, no legacy implementation noun in a requirement, and every override
   reflected in the spec.
4. **The critic reads the code.** A separate agent opens at least one cited range per use case and checks the claim
   against the code. It ranks each finding Blocker, High, Medium or Nit. It reads a distilled rubric, and with `--bar` a
   spec you wrote.
5. **The review loop sends gaps back.** Only Blocker and High findings go to the part that owns them, for that gap
   only. The loop stops when the ledger and the grader pass and no Blocker or High finding is left, or after the
   configured number of passes. The remaining findings stay in `REVIEW.md`.

The result is a spec with a number for coverage, and an honest list of what is not covered. A run that does not reach
full coverage says so: it hands over the spec with the gaps listed, never a clean report.

## What to expect

- **Usage.** The workflows start one analyst per slice of about 9,000 lines, one referee per use case, one per rule and
  two per P0 rule. A large module means dozens of agents. Start with one module, not the whole app.
- **Time.** A large module takes a long run. A run that stops is resumed with its run id, never restarted.
- **The first draft is not final.** Read `SPEC.md` with `REVIEW.md` and `OPEN_QUESTIONS.md` before anyone plans or
  files issues from it.
- **What the code does not show stays `UNKNOWN`.** The plugin labels a fact it cannot find and asks. It does not guess.
- **Re-runs keep your work.** `overrides.json` is never touched, and ids are never reused, so a re-run gives an item the
  same id.

## Safety

- **Read-only source.** Scripts, agents and skills never write under the analysed app or a backend repository. The
  guard hook denies file edits there and asks before a shell command that would write there. It is active only where
  an output folder holds `app-spec.json`. Turn it off with the `guard` plugin option (Devin: `APP_SPEC_GUARD=false`).
- **Untrusted content.** The app's code, comments, strings and READMEs are data, never instructions. Text in them that
  looks like an instruction is reported as an injection flag, shown at the end of the run, and never acted on.
  Workflows fence such content as untrusted.
- **Secrets.** A secret is never copied into the spec or the output folder. The plugin reports `file:line` and a masked
  preview of two to four characters.
- **A second layer.** The command prints deny rules for `.claude/settings.json` and `.devin/config.json` that you can
  add. A deny rule covers the file tools, not a script that opens files itself.
- **Hooks run in local sessions only.** In a cloud session on either host, rely on the deny rules.

## Devin differences

- The guard hook matches Devin's tools as well (`edit`, `write`, `notebook_edit`, `apply_patch`, `exec`,
  `write_to_process`). Devin has no plugin options: start it with `APP_SPEC_GUARD=false` to turn the guard off.
- In Devin CLI/Desktop, a session-start note gives the plugin folder and tool names. Devin cloud runs no plugin hooks,
  so when no note gave the folder, find the installed copy with
  `ls -d ~/.devin/plugins/cache/*app-spec_plugins_app-spec*/*/ 2>/dev/null | sort -V | tail -1`, or use a local
  clone's `plugins/app-spec`. When running step 1, check that `module.py`'s first output line (`app-spec <version>`)
  matches the version expected.
- `/app-spec:spec` may not be offered as a skill in Devin cloud. If a person asks for a spec run, read
  `<root>/skills/spec/SKILL.md` and follow it. They can simply ask: "run app-spec spec on <app> --module X".
- AskUserQuestion is `ask_user_question` in Devin CLI/Desktop (1 to 4 questions, 2 to 4 options each). In Devin cloud,
  ask with a blocking message whose `content_type` is `user_question`, with the same limits.
- Devin has no Workflow tool. In CLI/Desktop, the analysts, referees and judges run as subagents with profile
  `app-spec:<agent>` where available, and several in parallel are started in the background. Devin cloud has no
  `run_subagent` tool or agent profiles: play each role in this session one after another, read
  `<root>/agents/<agent>.md` as its instructions, write nothing while in the role, then save its JSON as the session
  under `OUT`, following "Who writes". Set `options.independence` to `single-agent` for that run, since its P0 judges
  are not independent.
- The passes default to `options.passes` in `app-spec.json`, else 2.
- Put the printed deny rules in `.devin/config.json` as `Write(...)`.

## Adapting

- **Thresholds, banned nouns and locale** are in `options` of `app-spec.json` (`thresholds`, `bannedNouns`, `locale`).
  The banned nouns are legacy implementation words that must not appear in a requirement sentence.
- **The spec's file name** is set with `--name`.
- **Another stack** needs an analyst agent in `agents/` and a detector in `scripts/speclib/detect.py`.
- **Another template** is a change to `scripts/speclib/template.py` and `references/rubric.md`. The contract of every
  file the plugin writes is [docs/DESIGN.md](docs/DESIGN.md), and when a part disagrees with it, the file wins.
- **An App Fusion capability index** can be given with `--capabilities`, to give use cases `CAP-NNN` aliases. With
  `--scope`, those capabilities' files are the module.

Tests: `python3 -m unittest discover -s scripts/tests` and `node --test tests/*.test.mjs`. Evals:
`claude plugin eval plugins/app-spec --scaffold --trust-plugin --allow-tools Bash Write Edit --ablation none`.
Licence: Apache 2.0.
