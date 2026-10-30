# app-spec: a module-to-spec tool for porting features into a new app

Design document, 2026-10-30. Working name `app-spec`; the repository and plugin take the same name until Dan renames them.
Status: draft for Dan-Mihai Cuc's approval. Nothing is built before approval. After approval this file moves into the
new repository as `docs/superpowers/specs/2026-10-30-app-spec-design.md`, its first commit.

Decisions in this document are Dan's where the text says "Dan decided". Everything marked **my call** is the
author's default; Dan can overrule any of them. Everything under "Left to the builder" is deliberately open.

---

## 1. Intent

A developer points a command at **one module of one existing mobile app**, for example the payslips module of
me-ios, and gets back a **spec** that is complete and deep enough to plan and build the same feature in a new app
without reading the old code again. The same spec is the source for the new app's UI and end-to-end tests, and,
when the developer wants it, for a screen-and-field comparison between the old app and the new one.

### Why this exists

- App Fusion (`danchily2/app-fusion`) understands legacy apps well: inventories, capability maps, business rules
  with citations, referees. It has **no spec step**. During the Dreamshot week (2 to 12 October 2026) the Scarlet
  iOS repository got one of its own: `.agents/skills/spec/SKILL.md`, ported from me-android, which writes
  `docs/specs/<feature>.md` from a GitHub issue or a `CAP` list by reading the fusion program's catalogs
  (`capability_index.json`, `FUSION_BRIEF.md`, `rules.json`, the decisions and evidence files) and investigating each
  capability in the reference repositories and in Figma. A sibling skill, `/issues`, turns that spec into an epic
  and PR-sized issues. The calendar spec that sets this tool's bar was produced that way, headless, by Devin.
- That skill cannot run on **one module of one app**: it needs a fusion workspace, a GitHub issue or capability ids,
  and the program's rules and decisions. `app-spec` is the standalone producer. It replaces the program inputs with
  its own understanding of the module, keeps the same output template so `/issues` and the plan skills keep
  working, and adds what the program never measured: a coverage ledger and a review pass.
- App Fusion's program (brief, approval, hashed proof) is sized for a whole fusion. The teams port **one feature at
  a time** through issues and pull requests, and the program's build and verify loop was never used.
- Michal Melich's requirements for the port: a spec per feature plus a description of what to follow in the new
  app; tests that can run against the old app first; units small enough for one session's context; no legacy debt
  carried over. This tool answers the first three directly and the fourth by construction.

### The one-sentence test of success

A developer who has never opened me-ios can plan and build payslips in Scarlet from the generated spec and tests,
and the optional old-app comparison catches any field they missed.

---

## 2. Goals, non-goals, anti-goals

### Goals

1. **One module, one command, one spec.** Input: a path to an app and a module name or a set of folders. Output: a
   reviewed spec a person reads, in one session.
2. **Completeness is measured, not assumed.** A deterministic inventory of the module (screens, fields, routes,
   endpoints, string keys, events, storage keys, permissions) is the checklist. Every item is attached to a use case
   or listed as uncovered with a reason. The spec carries the ledger.
3. **Depth at the bar of the calendar spec.** Dan decided: `scarlet-team-c/docs/specs/calendar-and-absence-for-me-and-for-my-team.md`
   (15 capabilities, 37 acceptance criteria) is the bar. Each use case carries its rules with concrete values, its
   states, its error and offline paths, its permissions, its endpoints with request and response fields, and its
   copy. A screen described without its states is a defect the review catches.
4. **Reviewed before a person reads it.** A critic grades the draft against the bar and the ledger and sends targeted
   gaps back for another pass, at most twice, before the spec is handed over with the remaining findings attached.
5. **Tests from the spec.** Maestro flows for the new app, built as shared assertion subflows (what is on the screen
   and what happens) plus per-app navigation subflows (how to get there), so navigation can differ between the old
   and the new app while the assertions stay the same. Unit-test skeletons per business rule, named by rule id.
6. **Optional comparison with the old app.** Dan decided what "done" looks like: layouts are similar, the new app has
   roughly the same screens, and no field is missing. The comparison is a screen-and-field parity check driven by
   the same field inventory, asserted by accessibility id on the new app and by id or by static label on the old
   app, run on both, with a report a person reads. Not a pixel diff. Dan decided it must work before the old apps
   carry ids, because those ids are planned but cannot be relied on.
7. **Claude Code and Devin**, the way App Fusion does it: the same plugin layout, a Devin meta-plugin, a session note
   for Devin, a guard hook that knows both tool sets, and a "without the Workflow tool" path for every fan-out.
8. **Standalone.** No fusion workspace, no program, no brief. When a fusion workspace exists, the tool can take its
   `capability_index.json` to reuse `CAP-NNN` ids, but it never needs it.

### Non-goals

- Fusing several apps. No twins, no conflicts, no fusion classes. One app in, one spec out. (Dan decided.)
- Reading Figma or any design tool. The spec documents the module as it exists today. The new design is someone
  else's input to the plan.
- An approval gate, hashed evidence, canaries or a verdict file. The spec is reviewed by a person; the tests are run
  by the new app's own pipeline. A person's **corrections do persist**: `overrides.json` (5.9) records dropped or
  renamed items, id mappings and rejected use cases with reasons, every command honours it, and a re-run of `spec`
  never overwrites it.
- Writing production code in the new app.
- Editing the source app. The guard denies it. The old-app comparison needs accessibility ids on the old screens; the
  tool lists what is missing and can write a patch file, and a developer lands it as a normal pull request.

### Anti-goals: what would make it a failure even if it runs

- **Shallow.** Screens described as what they show, not what they do. Rules without values. "Handles errors"
  without which errors and what the user sees. Dan: a shallow spec goes back.
- **Silently incomplete.** A use case or a screen the code has and the spec lacks, with no line saying so. Dan: an
  incomplete spec goes back.
- **Legacy structure as requirements.** View-model names, dependency-injection shapes, Realm models, notification
  broadcasts or god objects presented as things to build. The spec records behaviour to keep and names the
  implementation to drop, per use case.
- **Invented facts.** An endpoint, field, permission or copy that no line of code supports. Every claim is cited or
  marked UNKNOWN with what was searched.
- **Unreadable.** A 3,000-line wall. The spec has a one-page summary, one section per use case, and tables where the
  team's hand-written specs use tables.

---

## 3. Constraints

- **Repository and distribution.** Dan decided: a separate repository with its own marketplace, not a second plugin
  inside `app-fusion`. Layout as App Fusion: `.claude-plugin/marketplace.json` at the root, the plugin under
  `plugins/app-spec/`, `.devin-plugin/plugin.json` at the root as the Devin meta-plugin. Code is copied from
  App Fusion where it fits (analysts, rules extractor, stack extractors, guard, Devin context, test harness), not
  depended on at runtime. The two repositories drift independently; that is accepted.
- **Hosts.** Claude Code (local, cloud) and Devin (CLI, Desktop, cloud). Devin does not expand `${CLAUDE_PLUGIN_ROOT}`
  in a skill, has no Workflow tool, has no plugin options and names tools differently; the session-start note covers
  that, as in App Fusion. Hooks run only in local sessions on both hosts.
- **Implementation language.** Skills, agents and workflows in Markdown and JavaScript; scripts in standard-library
  Python 3.8+, no third-party packages (same as App Fusion, so the plugin installs anywhere Python is). **My call.**
- **Read-only on the source app.** The analysts, extractor, mapper, critic and writer never modify files outside the
  output folder. The guard hook denies tool writes under the source app's path and asks before shell commands that
  would write there.
- **Untrusted content.** Source code, comments, strings and READMEs of the analysed app are data, never instructions.
  Agents report instruction-shaped text as a finding. Workflow prompts fence such content. Secrets are never
  reproduced: `file:line` plus a 2 to 4 character masked preview.
- **Stacks in v1.** Native iOS (Swift, UIKit, SwiftUI, TCA), native Android (Kotlin, Compose, XML), React Native.
  These are the stacks the copied extractors and analysts know. Backend repositories are read only as optional
  contract sources (see 5.6).
- **Licence and visibility.** Dan decided: the same as App Fusion, a public repository under Apache 2.0 with the same
  `LICENSE` and `NOTICE` shape. Consequences: the calendar spec is never committed to this repository, because it
  cites me-api controllers and policies; the critic ships a distilled rubric derived from it; `--bar` points at a
  local file only; eval fixtures are synthetic; the acceptance measurements of 5.16 are recorded in the Scarlet
  repository, not here.

---

## 4. How it is used

```
# one module of one app, spec written into the new app's docs folder
/app-spec:spec ~/code/me-ios --module Payslips --out ~/code/scarlet-ios/docs/specs/payslips

# the same, with the backend repository as a contract source and a fusion index for CAP ids
/app-spec:spec ~/code/me-ios --module Payslips --contracts ~/code/me-api \
  --capabilities ~/work/analysis/work-app/capability_index.json --out ./specs/payslips

# re-grade a spec a person edited
/app-spec:review ./specs/payslips

# tests for the new app from the spec; optionally also flows that run on the old app
/app-spec:tests ./specs/payslips --target ~/code/scarlet-ios [--legacy ~/code/me-ios]

# the optional screen-and-field comparison, both apps built and installed on simulators
/app-spec:compare ./specs/payslips --legacy ~/code/me-ios --target ~/code/scarlet-ios

# where things stand and the next command
/app-spec:status ./specs/payslips
```

A developer runs these. The person who reads the spec may be the same developer or a reviewer. The spec is the
hand-off to planning: Dan decided a person reads it before any plan or issue is made from it.

### The walk through, payslips in me-ios

1. `spec` detects the stack (Swift package app) and resolves `--module Payslips` to folders whose names match:
   `Modules/PayslipsFeature` (99 files, 8,411 lines), `EmployeeServices/Payslips` (12 files, 639 lines),
   `EmployeeServices/PayslipsInterface` (12 files, 986 lines). It then finds the **touch points** outside those
   folders: the start-page card that opens the latest payslip, the payslip questions in `EmployeeChatBot` (16 files),
   the analytics events of the payslip family, the 50 string keys containing "payslip" in `EmployeeResources`, and
   the navigation entries that lead into the module. It shows core files, touch points and string keys, and asks for
   a yes. Headless, it proceeds with the proposal and records that nobody confirmed it.
2. It inventories the module deterministically and shards it (about 9,000 lines per shard, so two or three shards
   here plus one for touch points).
3. Analysts read each shard and return use-case fragments with evidence. A mapper merges them into use cases
   (`UC-001` and so on) and flows through the module. A referee re-checks every citation.
4. The rules extractor returns rule cards per shard; a referee checks each citation; P0 rules get two judges.
5. The contract reader resolves every endpoint the module calls, with request and response fields from the app's
   request and model types, and, when `--contracts ~/code/me-api` is given, from the backend's controllers and DTOs.
6. The spec writer compiles the catalogs into `SPEC.md` in the bar's format. The ledger script attaches every
   inventory item to a use case or lists it as uncovered.
7. The critic grades the draft: coverage from the ledger, depth per section against the bar, legacy leakage,
   invented facts (citations that do not resolve). Blocker and High findings go back to the agent that owns that
   section, for that gap only. Two passes at most.
8. `SPEC.md`, `LEDGER.md`, `REVIEW.md` and `OPEN_QUESTIONS.md` are written. The report names the coverage, the
   number of use cases, rules, criteria, open questions, and the next command: a person reads the spec.

---

## 5. The parts

### 5.1 Commands (skills)

| Command | Does | Writes |
| --- | --- | --- |
| `spec <app> --module <name or paths> [--out DIR] [--name FILE] [--contracts REPO ...] [--capabilities FILE [--scope CAP,...]] [--bar FILE] [--passes N] [--headless]` | The whole pipeline, sections 5.2 to 5.8 | the output folder, section 5.9 |
| `review <out>` | Runs the ledger and the critic on the current `SPEC.md`, which a person may have edited; writes a new `REVIEW.md`; applies nothing | `REVIEW.md`, `ledger.json` |
| `tests <out> --target REPO [--legacy APP] [--stack S]` | Generates Maestro assertion subflows, navigation subflows and unit-test skeletons for the target; optionally the legacy navigation subflows and the list of ids the old app lacks | `tests/` in the output folder, and, on request, into the target repository's test folders |
| `compare <out> --legacy APP --target REPO [--device ...]` | Runs the shared assertions on both apps and writes the parity report | `compare/` |
| `status <out>` | Where things stand: coverage, passes, open questions, what exists, the next command | nothing |

Every command ends by naming the exact next command. `spec`, `tests` and `compare` can only be started by a person
(`disable-model-invocation: true`), because they read a codebase and, for `compare`, run apps. `review` and
`status` may be invoked by the model.

### 5.2 Module resolution (`scripts/module.py`)

- Input: the app path and `--module`, either a name or one or more folders or globs.
- Stack detection reuses App Fusion's `detect.py`.
- A **name** is matched case-insensitively against package names, module folders, feature folders and screen or
  route names from the inventory. Candidates are shown with file and line counts.
- **Touch points** are found from the core folders outward: types and request classes the core defines and others
  use; string keys the core's screens use and where else they are used; analytics event families; navigation
  entries (routes, coordinators, tab items, deep links) that lead into the core; home or start-page components that
  show the module's data; assistant or chat tools that call the module's services. Each touch point is a file with
  the reason it was pulled in.
- **A second front door, by capability ids.** With `--capabilities <capability_index.json> --scope CAP-225,CAP-226,...`
  the scope is the union of the files those capabilities cite for this app in the fusion index, plus their touch
  points. This is how a Scarlet phase, which spans folders, becomes a module scope without a fusion workspace being
  needed at run time. **My call**, added after the builder check; it costs one resolver in `module.py`.
- The proposal (core, touch points, string keys, estimated shards) is shown; a person confirms or edits. Headless
  runs take the proposal and record `confirmed: false` in `app-spec.json`.
- Output: `module.json` with `core`, `touchPoints`, `stringKeys`, `shards`, every file relative to the app root.
- Sizing from me-ios: payslips is about 10,000 lines in three folders, two shards. `Modules/CalendarFeature` alone is
  336 files and 40,767 lines, five shards, before its services and start-page touch points.

### 5.3 Inventory (`scripts/inventory.py`, module-scoped)

Copied from App Fusion's `inventory.py` and `fusionlib` extractors, scoped to the module's files, with one addition.

- Per the existing extractors: screens (view controllers, TCA features, SwiftUI views, Compose screens, React Native
  screens), routes and navigation, endpoints with constants resolved, analytics events, string keys with locales,
  storage keys and models, permissions and platform items, dependencies the module pulls in.
- **New: the field inventory** (`fields.json`). For each screen, the candidate elements a user reads or acts on:
  texts, inputs, buttons, toggles, pickers, lists and their row kinds, images and documents, with the string key
  each shows and the accessibility id or test tag it already has. This is deterministic and heuristic per stack
  (SwiftUI and UIKit element types, Compose composables, React Native components); the analysts confirm and name
  the elements. The field inventory is what the screen-and-field comparison asserts.
- Every count is printed with the rule that produced it, as in App Fusion.

### 5.4 Understanding (`workflows/understand-module.js`, agents)

- One stack analyst per shard (`ios-analyst`, `android-analyst`, `rn-analyst`, copied from App Fusion unchanged)
  returns **use-case fragments**: name (verb first, in business words), description, personas and permissions,
  screens, files, endpoints, events, string keys, storage, platform features, a rules hint, and evidence. Same shape
  as App Fusion's fragment schema.
- One **use-case mapper** (`agents/use-case-mapper.md`, adapted from the capability cartographer for one app)
  merges fragments into use cases, one per user outcome, splits fragments that mix outcomes, groups use cases into
  screens and **flows** through the module (3 to 8 steps, each naming its use cases), and keeps every piece of
  evidence. No fusion classes, no twins.
- One **referee** per use case re-checks the citations against the code and rejects a use case no executable code
  implements. The referee is the stack analyst with a referee prompt, as in App Fusion's workflows.
- Ids: `UC-NNN`, `SCR-NNN` (screens), `FLOW-NNN`, issued by the render script and stable across re-runs by
  normalized name and evidence, as App Fusion's `render.py` does. With `--capabilities`, a use case whose outcome
  matches a capability in the index takes that `CAP-NNN` as an alias, printed next to the `UC` id.
- Without the Workflow tool (Devin, or a Claude Code session without it): one analyst per shard group of up to about
  25,000 lines, at most six in parallel, then one mapper, then one referee pass; the skill says so step by step.

### 5.5 Rules (`workflows/extract-rules.js`)

- App Fusion's `extract-rules.js` and `business-rules-extractor.md`, with the conflict phase removed (one app). One
  extractor per shard, one citation referee per rule, two judges per P0 rule. Rules attach to use cases.
- Cards keep App Fusion's shape: plain English, Given/When/Then with concrete values, parameters with current values,
  priority P0 to P2, confidence, the question for the owner below High, `suspectedDefect`.
- Ids `RULE-NNN`, stable across re-runs.

### 5.6 Contracts (`agents/contract-reader.md`, `scripts/contracts.py`)

The calendar spec's depth comes largely from its endpoint table: method and path, auth and request fields, response
model fields, errors and the UI reaction, each cited in the app **and** in the backend. The bar requires this.

- From the app alone: every endpoint the module calls, with constants resolved, the request type and its fields,
  the decoded response model and its fields, the error handling and what the user sees. VERIFIED when read in the
  app's code.
- With `--contracts <repo>` (one or more backend repositories, read-only): the contract reader locates the route in
  the backend (controller attributes, route helpers, DTOs), confirms method, path, authorization policy, required
  query or body fields, response DTO fields and documented status codes, and reports where the app and the backend
  disagree (a field the app decodes that the DTO does not define, as the calendar spec found for the combined
  balances). Framework support in v1: ASP.NET Core attributes and route helpers (me-api) and Express or NestJS
  decorators; others degrade to "app-only, backend UNKNOWN". **My call** on the frameworks.
- Output: `endpoints.json` with `EP-NNN` ids, and the endpoint table in the spec.

### 5.7 Writing the spec (`agents/spec-writer.md`, `scripts/render.py`)

The spec is compiled from the catalogs, never from memory. `render.py` writes the tables and ids; the spec writer
writes the prose sections (summary, purpose and states per screen, porting notes, keep-or-drop, open questions)
from the catalogs and the cited code, and never adds a fact without a citation.

**Format.** The first eight sections are **exactly** the template of Scarlet's `/spec` skill, same headings, same
order, so `/issues`, `create-plan` and `implement-issue-workflow` read an `app-spec` output without change. The
material the template has no place for follows as appendices. **My call**, made after the builder check; Dan's
answer to open point 1 can change it.

Header lines as the template: `Source: module <name> of <app> (no source issue)`, `Reference HEADs:` with the app's
commit and each contract repository's commit, then the module scope (core folders and touch points) and the
evidence labels (VERIFIED, INFERRED, UNKNOWN; `PROPOSED` for anything the writer suggests).

1. **Summary.** What the user can do, in three to five sentences, with the personas and the flows.
2. **Capabilities.** The template's table: `| CAP | Name | Design | Screens | Notes |`. The id column carries the
   `UC-NNN` id, or the `CAP-NNN` alias when the fusion index matches. `Design` is `carry-as-is (<app> <file:line>)`
   for every row, because this tool reads no design; a person changes it when a design exists.
3. **Screens.** Per screen or screen group: purpose, content, actions, and every state (loading, empty, error,
   success, offline, no permission, confirmation) with what the user sees. Source lines per the template. The
   fields and controls and their accessibility ids are summarized here and listed in full in Appendix A.
4. **Endpoints.** Per endpoint: method and path, auth policy or token, request model, response model with field
   types and nullability, error codes and the UI reaction. Backend citation when a contract source was given,
   otherwise INFERRED with the client citation and an open question, as the template demands.
5. **Business rules and permissions.** Validation, calculations, defaults, ordering, offline behaviour, flags, role
   and permission gates, each labelled and cited. The rule cards of 5.5, P0 and P1 first.
6. **Acceptance criteria.** Numbered across the whole spec as `AC<N> (<UC or CAP id>): ...`, each observable on
   screen so a Maestro flow or a `TestStore` test can assert it. At least one per P0 and P1 rule and per state that
   changes what a user can do. Not checkboxes: `/issues` parses this numbering.
7. **Dependencies and decisions.** What must exist or be decided first. For a standalone run this holds the
   module's dependencies on other modules (sign-in, shared clients, start page) and the decisions the spec needs
   from a person, each as a question with the options the code suggests.
8. **Open questions.** Every UNKNOWN, with what was searched and who can answer, each with an id.

Appendices, after the eight sections:

- **A. Fields and ids.** Per screen, every field and control from the field inventory: kind, the string key it shows,
  the accessibility id it has in the old app or the id proposed for the new one. This is the contract `tests` and
  `compare` assert.
- **B. Data.** Entities and fields the module reads and writes, local storage and its lifetime, caching and refresh.
- **C. Behaviour to keep, implementation to drop.** The behaviour the new app must keep, by rule and flow id, and the
  implementation facts that are not requirements (persistence technology, broadcast-based refresh, view-model
  structure, duplicated models), each with the file it came from. This is where the debt stays behind.
- **D. Strings, analytics and platform.** Keys and source-language text per screen with their locales; events per
  use case with properties; permissions, push categories, deep links, extensions, background work, sharing.
- **E. Flows.** The flows through the module, numbered steps naming screens and use cases. These become the
  end-to-end tests.
- **F. Coverage.** The ledger summary: per class, covered and uncovered counts, and the uncovered items with reasons.

**Length.** The header, summary and capability table fit on one page. The rest is as long as the module needs; the
calendar spec is about 280 lines for 15 capabilities, which is the expected order of magnitude for the eight
sections. The appendices add to that and are read when needed.

### 5.8 Review (`scripts/ledger.py`, `scripts/grade.py`, `agents/spec-critic.md`)

Two layers, one deterministic and one judged.

- **The ledger** attaches every inventory item (screen, field, route, endpoint, string key, event, storage key,
  permission, platform item) to the use case and section that covers it, by id references in the catalogs. Items
  with no reference are uncovered. Coverage is reported per class. Thresholds, **my call**, overridable in
  `app-spec.json`: screens, endpoints, events, permissions and storage keys at 100 percent; string keys and fields at
  95 percent; anything uncovered must carry a reason (`not user-facing`, `dead code`, `out of module`) or it fails.
- **The grader** checks shape: the eight template sections present, in order, with the template's headings; every
  use case has at least one rule or a stated "no client-side rule, server decides" with a citation; at least one
  acceptance criterion per use case, numbered `AC<N> (<id>)` across the spec; every citation resolves to an existing
  file and a line range inside it; UNKNOWN items have a search note and an owner; no duplicate use cases by
  normalized name; no banned legacy nouns in requirement sentences (a configurable list: Realm, Swinject,
  NotificationCenter, ViewModel, Redux, and so on) outside Appendix C; every entry in `overrides.json` is reflected
  (a dropped field is absent from Appendix A and listed in Appendix F with its reason).
- **The critic** (`spec-critic.md`, written new, in the stance of App Fusion's architecture critic) reads the draft,
  the bar, the ledger and samples of the cited code, and reports findings ranked Blocker, High, Medium, Nit: a
  screen without states, a rule without values, an error path the code has and the spec lacks, a use case the code
  has and the spec lacks, legacy structure stated as a requirement, a claim the citation does not support. Each
  finding names the section and the fix.
- **The loop.** Blocker and High findings are sent back to the owning agent with the finding and the relevant code,
  for that gap only. Then ledger, grader and critic run again. At most `--passes` rounds, default 2 (**my call**).
  What remains is written to `REVIEW.md` with the scorecard of every pass, so the reader sees what the tool could
  not fix and why.

### 5.9 Output folder

```
<out>/
  app-spec.json         source app path and commit, stack, module scope, contract sources, options, confirmations
  overrides.json        a person's corrections: dropped or renamed fields and screens, id mappings, rejected or merged
                        use cases, each with a reason; written by a person or by `review --accept`, never regenerated
  module.json           core files, touch points, string keys, shards
  inventory.json, INVENTORY.md, fields.json
  shards/<id>.json      what each analyst reads
  use-cases.json        UC-NNN with evidence, screens, flows
  rules.json            RULE-NNN cards
  endpoints.json        EP-NNN with request and response fields, errors, backend verification
  strings.json, events.json, storage.json, platform.json
  ledger.json, LEDGER.md
  review.json, REVIEW.md
  SPEC.md               the deliverable
  OPEN_QUESTIONS.md
  tests/                from `tests`: assert/, nav/<app>/, flows/, unit/, ids.json, ids-needed.md, legacy.patch
  compare/              from `compare`: PARITY.md, junit/, shots/
```

`SPEC.md` can be named after the module with `--name`, so it sits next to the team's existing specs as
`docs/specs/payslips.md`. The JSON files are the machine side; `review`, `tests` and `compare` read them and
`overrides.json`, never the Markdown. A re-run of `spec` regenerates every file except `app-spec.json` and
`overrides.json`, and keeps ids stable by normalized key, as App Fusion's `render.py` does. A person who edits
`SPEC.md` by hand records the change in `overrides.json` too, or `review` reports the drift between the two.

### 5.10 Tests (`scripts/testgen.py`, `agents/test-writer.md`, `references/targets/*.md`)

- **Shared assertion subflows**, one per screen and state: `tests/assert/SCR-004-payslip-detail.yaml` asserts, by
  accessibility id, every field and control of the screen's field inventory and the state's visible texts where
  stable. They contain no navigation.
- **Navigation subflows**, one per flow per app: `tests/nav/target/FLOW-002.yaml` reaches the screen in the new app;
  `tests/nav/legacy/FLOW-002.yaml` (with `--legacy`) reaches it in the old app. Flows compose them with `runFlow`.
- **Flows**, one per `FLOW-NNN`, calling the navigation subflow of the app under test and the assertion subflows of
  the screens it passes.
- **The id contract**, `ids.json`: the accessibility ids each screen must expose, taken from the old app where it
  has them and proposed as `<module>.<screen>.<element>` where it does not. The spec's Appendix A prints them, so
  the new app's components carry them from the first commit. `ids-needed.md` lists the old app's elements that
  lack an id, with `file:line`; `legacy.patch` is an optional, reviewable patch a developer applies in the old
  repository as a normal pull request. The tool never writes into the old app.
- **Old-app assertions without ids.** Dan decided the comparison must not depend on ids in the old app. Each field
  in the inventory therefore carries two selectors: the id, and the **static label** it shows, resolved from the
  old app's string catalogue at a fixed run locale (English by default). The generator writes the assertion
  subflows in two variants from the same `fields.json`: `assert/<SCR>.ids.yaml` for the new app and
  `assert/<SCR>.labels.yaml` for the old app, where each element is asserted by its id when the old app has one and
  by its static label otherwise. Maestro matches `text:` against the accessibility label, which on iOS and Android
  is the visible text for labelled controls. Elements with no static label (icon-only buttons, pure data values,
  images) are **not comparable without ids**; they are listed as such per screen, never silently passed. When ids
  land in the old app later, `ids.json` is updated and the labels variant shrinks on its own. Michal's objection to
  text selectors holds for data and for mixed locales; it does not hold for static copy at one locale, which the
  spec knows key by key. **My call** on the mechanism, Dan's on the requirement.
- **Unit-test skeletons**, one failing test per rule with the card's concrete values, named by rule id and use case,
  for the target stack: Swift Testing with TCA `TestStore`, JUnit with Kotlin, Jest. Stack profiles are copied from
  App Fusion's `references/targets/` and name the test commands and conventions. Scarlet's own conventions (ids over
  text, `scrollUntilVisible` before interaction, no point taps on app controls) are followed; the profile for
  Scarlet iOS and Android is written from their `AGENTS.md` files. Both Scarlet apps are v1 targets. **My call.**
- **Skeletons never break the target's build.** They are written as templates (`RULE-023-certificate-percentage.swift.txt`)
  under `tests/unit/`, because a `TestStore` test for a reducer that does not exist yet would fail `swift test` for the
  whole package and Scarlet's PR gate with it. `--target` writes Maestro flows into the target's `.maestro/` folder,
  which compiles nothing, and copies unit templates only with `--write-unit-tests`, into the test target the
  developer names, with the `.txt` suffix removed. **My call**, after the builder check.
- **Demo mode by default.** Scarlet's flows launch with `demo: true` against preview fixtures and must stay
  credential-free; stage flows live in `Scripts/ci/`. Generated target navigation subflows therefore start with the
  target profile's demo launch arguments and land in `.maestro/`. With `--stage` they start with the sign-in steps
  the profile names and land where the profile puts credentialed flows. The old app runs against stage, so the
  comparison in 5.11 asserts **presence**, never values or counts. **My call.**

### 5.11 Compare (`scripts/compare.py`)

- Preconditions: both apps built and installed on booted simulators or emulators; Maestro on the path; test
  accounts and a stage backend named by the developer; the old app running at the fixed locale. Ids in the old app
  are welcome and not required (today me-ios has 138 `accessibilityIdentifier` uses in all, 30 of them in the
  calendar module and none in payslips). The command never uses production.
- `--legacy-mode ids|labels|auto` (default `auto`): per element, id when the old app has one, static label
  otherwise, as 5.10 describes. A second source of presence on the old app is the view hierarchy: after each
  navigation subflow the command dumps the screen's hierarchy (`maestro hierarchy`) and `compare.py` matches its
  elements to the field inventory by label, which catches fields the label assertions could not express. Both
  sources are reported; neither judges layout.
- `PARITY.md` has three lists per screen: present on both, **missing on the new app**, and **not comparable without
  ids** on the old app. The third list is the honest cost of running before the ids land, and it is the list that
  `ids-needed.md` is sorted by, so the first id pull request removes the most of it.
- Runs every flow twice: legacy navigation plus shared assertions on the old app, target navigation plus the same
  assertions on the new app, with `--format junit`. Takes one screenshot per screen on each side.
- Fields the spec marks as dropped in `overrides.json` are excluded with the reason; screenshot pairs follow each
  screen for a person's glance. No pixel comparison, no layout judgement. Pass means no field present on the old app
  is missing on the new one, among the comparable fields; the not-comparable list is printed in the summary so a
  pass is never mistaken for a complete check.
- A flow that cannot run (no build, no device, no account) is reported as not run, never as a pass.

### 5.12 Agents

| Agent | Origin | Role |
| --- | --- | --- |
| `ios-analyst`, `android-analyst`, `rn-analyst` | App Fusion, unchanged | read shards, return fragments; referee citations |
| `use-case-mapper` | from `capability-cartographer`, single-app rewrite | fragments to use cases, screens, flows |
| `business-rules-extractor` | App Fusion, unchanged | rule cards |
| `contract-reader` | new | endpoints with fields and errors, app and backend |
| `spec-writer` | new | prose sections from catalogs, citations only |
| `spec-critic` | new, stance from `architecture-critic` | grades the draft against the bar and the ledger |
| `test-writer` | from `test-engineer`, no canary or evidence runner | flows and unit skeletons |

All are read-only except `test-writer`, which writes only under `tests/` or the target repository's test folders.

### 5.13 Workflows

`understand-module.js` (analysts, mapper, referees) and `extract-rules.js` (extractors, referees, P0 panel) for the
Workflow tool, both resumable with a run id. Spec writing, review and test generation are single agents called from
the skill, so they need no workflow. Every skill gives the no-Workflow path.

### 5.14 Devin and Claude Code

Copied from App Fusion: `hooks/hooks.json` with the guard on `Edit|Write|MultiEdit|NotebookEdit|Bash` and Devin's
`edit|write|notebook_edit|apply_patch|exec|write_to_process`; `hooks/devin-context.sh` and `scripts/devin_context.py`
printing the plugin's real folder, the tool-name mapping, the no-Workflow instruction and the option defaults;
`APP_SPEC_GUARD=false` to turn the guard off in Devin; deny rules printed for `.claude/settings.json` and
`.devin/config.json`. The guard finds `app-spec.json` from the output folder named in the command, the project folder
or the paths a tool call names, and denies writes under the source app path it records.

### 5.15 Tests and evals of the plugin itself

As App Fusion: Python `unittest` for the scripts (module resolution, inventory on fixture apps, ledger, grader,
render ids stable across re-runs, test generation), the Node harness for the workflows' control flow with stubbed
agents, `claude plugin validate`, and three `claude plugin eval` cases on tiny fixture apps: `spec` produces a spec
whose ledger covers the fixture; the guard refuses an edit to the source app; `status` names the right next command.

### 5.16 Acceptance of the tool

Two runs decide whether the tool reaches the bar.

1. **Calendar, me-ios.** Run `spec` on `Modules/CalendarFeature` plus its touch points, with me-api as a contract
   source. Compare the generated spec with the existing calendar spec, **scoped to the rows whose cited me-ios files
   fall inside the resolved module**: the personal-information form (CAP-213, Dottie) and anything cited only in vmm
   or me-android are out, as are decisions and Figma ids. Matching: endpoints by method and normalized path; screens
   by normalized name or by an overlapping cited file; rules by an overlapping cited `file:line` range, falling back
   to the plain-English sentence; criteria by the rules and screens they cite. The generated spec must cover at least
   90 percent of the in-scope endpoints, screens and rules (**my call** on the number), and a person reads the diff
   both ways. The same run, with `--capabilities ... --scope` set to the phase's capability ids, is the test of the
   second front door and should reach the rows the folder scope cannot.
2. **Payslips, me-ios.** The first real module. A developer plans and builds from it in Scarlet. The `tests` and
   `compare` commands run against the Scarlet payslips that exist from Dreamshot. The time from command to a spec a
   person accepts, and the findings the person still had to add, are recorded in the repository as the tool's first
   measurement.

---

## 6. Left to the builder

- The field-inventory heuristics per stack: which element types count, how text and key references are resolved,
  how list rows are represented. Precision is preferred over recall; the analysts fill the gaps.
- The exact JSON schemas, derived from App Fusion's fragment, capability and rule schemas with the single-app
  changes above.
- The accessibility-id naming scheme beyond `<module>.<screen>.<element>`, and how ids are matched when the old app
  uses a different convention.
- How the contract reader locates routes in ASP.NET Core and Express or NestJS, and how it degrades for others.
- How the critic samples code: which cited ranges to open, how many per pass.
- The banned legacy nouns list and how it is configured per app.
- The eval fixture apps: small, one per stack, with a known module and a known answer.
- Flag names and defaults not stated here; the `status.py` staleness rules (spec older than inventory, review older
  than spec, tests older than spec).
- Repository tooling: test runner, lint, changelog, release numbering (App Fusion's `CHANGELOG.md` convention).

---

## 7. Decisions from the builder check

The builder check, a fresh reviewer reading this document as the engineer who would plan it, raised seven
questions. Three were Dan's to answer; Dan answered them on 30 October 2026:

1. **`app-spec` replaces Scarlet's `/spec` as the producer** and writes the same eight-section template, so
   `/issues` and the plan skills consume it unchanged; the extra material is appendices (5.7). Dan: "ok".
2. **The comparison must work without ids in the old app.** Dan: the ids are planned but cannot be relied on. The
   design answers with the two-selector field inventory, label-based assertions at a fixed locale, the hierarchy
   dump, and the explicit not-comparable list (5.10, 5.11). `compare` ships in v1.
3. **Public, Apache 2.0, the same as App Fusion.** Dan: "same as app fusion". The consequences are in section 3.

Settled by the author after the builder check, each marked **my call** in the text: backend contract sources stay in
v1 (5.6); the output matches the `/spec` template exactly with appendices (5.7); scope by capability ids is a second
front door (5.2); corrections persist in `overrides.json` (5.9); unit skeletons are templates that never enter the
target's build unasked (5.10); generated flows run in demo mode by default and the comparison asserts presence only
(5.10, 5.11); both Scarlet apps are v1 test targets (5.10); the new app adopts the old app's ids where they exist and
the proposed `<module>.<screen>.<element>` scheme elsewhere (5.10).
