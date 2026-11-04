# Changelog

A release gets a new number in `.claude-plugin/plugin.json`. Claude Code only offers an update when that number
changes.

## Unreleased

Fixes found in the v8 payslips run (0.7.1).

- **A saved contract patch always reaches the endpoints.** In pass 2 the session saved `contracts/batch-4.json` and
  ran `merge_contracts.py OUT` without it (the skill's after-patch step names no file), so the corrected error
  reactions never reached `endpoints.json` and critic-3 raised them again as a Blocker and a High.
  `merge_contracts.py` now also folds every `contracts/batch-<k>.json` that no earlier merge folded, in batch order,
  and records the folded files, so an older batch never overwrites a later correction.

- **An event case gets its own line.** The iOS scan reported `exportAllPayslips` at the `enum Event` line and other
  cases one or two lines early, because the case pattern began its match on the blank lines above the case. The
  analyst gave the right lines, but nothing writes `inventory.json` again, so the critic raised it in every pass.
  The line now counts from the case name.

## 0.7.1 - 2026-11-03

- **A review patch can clear the out-of-scope list.** In v7b the critic raised year-end items that `out-of-scope.json`
  still listed in all 3 passes, while kept use cases covered them; the mapper sent their names in `remove`, but
  `remove` reached only use cases, screens, flows and rules, and the run recorded it in `MANUAL_STEPS.md`.
  `patch_result.py` now also removes a listed name from `outOfScope` (names match without bracket notes or capability
  ids), and the skill says so.

## 0.7.0 - 2026-11-03

- **Rule cards in behaviour words.** In every payslips run (v4, v5, v6) critic-1 raised rule cards that state old-app
  identifiers as values (`Date.distantPast`, `hasNextItems`, `isInitialLoading`, `reachabilityService.isOnline`),
  and the review loop could only fix the cards it was shown. The extractor prompt and agent now say to write the
  sentence, Given/When/Then, parameters and edge cases in behaviour words and keep the names in `source`; a server
  permission, API field, push payload key or string key may stay. A regex check was tried on the v6 rules and
  dropped: most of its hits were names the new app needs.

## 0.6.0 - 2026-11-02

- **A rules finding corrects the named cards instead of re-extracting the shard.** In v5 step 7.5 re-ran the
  extraction on each shard a rules finding cited. The new cards got new source keys, so `patch_result.py` added them
  beside the wrong old ones (87 rules became 162, with pairs such as RULE-031 and RULE-125), and critic-2 raised 4 of
  its 5 Blocker and High findings again on the old cards. The rules owner now gets the findings and the cards they
  name, keeps each card's name and source file so the corrected card replaces the old one, and lists wrong or
  duplicate cards in `remove`. The rules extractor prompt has a section for this second job.

- **An endpoint reached through a service can be verified, and an inferred one says why.** In v5 `allreports` and
  the report detail (request types outside the module, called from `ReportsService.swift`) stayed `INFERRED` with
  no reason, which the exit criteria do not allow. The calling file (`usedBy`) now counts as a client, so a use case
  that cites the service verifies the endpoint, and every `INFERRED` endpoint gets a `reason` that names the client
  files no use case cites.

- **The grader resolves a bare file name as the catalog check does.** In v5 the writer cited
  `MainPayslipFeature.swift:287-290` and `citations-resolve` failed with "file not found", while `render.py` accepts
  a bare name that exactly one file under the roots has. `grade.py` now resolves such a name to that file and checks
  the range there; a name no file or several files have still fails.

- **A run records which plugin made it (N1).** Devin's plugin cache stayed on an old version, and nothing in the run
  folder said which code had run. `module.py` now writes `plugin: {version, commit}` to `app-spec.json` (the commit
  is null for an installed copy, which has no git checkout) and prints `app-spec <version>` as its first line.

- **A shard keeps to one area (P5/P12).** Small folders were merged with their alphabetical neighbours, so a shard
  could hold `EmployeeServices/Payslips` next to `Modules/EmployeeAppCore`, named `[EmployeeServices/Payslips..
  Modules/EmployeeAppCore]`, and its analyst read unrelated code. Small parts now merge only within one top folder,
  and a merged shard is named by its folder and parts: `EmployeeServices/{Payslips, PayslipsInterface}`.

- **A large agent answer the harness stores as a file is saved directly.** In v5 the contract reader's answer for 10
  endpoints was 61.7 KB; the harness stored it as a tool-result file (a JSON list of `{type, text}` blocks) and
  showed a 2 KB preview, so the session could not copy it, and joined the blocks with a one-line script (recorded in
  `MANUAL_STEPS.md`). `save_json.py` now reads such a file as the joined text of its blocks, and the skill says to
  pass the stored file's path as it is.

- **A screen takes the fields of the sub-views it uses.** `PayslipRowView` and `PayslipDetailFooterView` (in the file
  of SCR-008) and `YearEndReportView` (its own file, used by SCR-011) belonged to no screen, so their 8 fields were
  uncovered and the ledger's fields class failed at 84.9 percent. A screen now also takes the `fields.json` elements
  of each view its file uses (`Name(`, `Name {`, `Name.init`) that is not a mapped screen itself. On the v4 folder
  the fields class reaches 100 percent.

- **The skill says which role writes (P9).** Every agent prompt says read-only, while the path without the Workflow
  tool (and Devin, where one agent plays every role) needs that agent to save results. The skill now states that the
  agents only return JSON, that only the session writes, under `OUT`, and that for one agent in every role
  "read-only" means writing nothing while it acts in a role, then saving the JSON as the session.

- **A rule names its use case by id and can name its conflicts (P23).** The rules schema had a free-text `useCase`,
  so a name copied with a small change lost the link to the use case, and no field said that two rules disagree.
  The extractor now copies the use case's id (`UC-NNN`) from the index (`render.py` still accepts a name from older
  results), and a new `conflictsWith` lists the rules that state the opposite. `render.py` turns those names into
  RULE ids, warns about a name no rule has, and the spec shows **Conflicts with** under the rule.

## 0.5.0 - 2026-11-02

Fixes found in the v4 payslips run (0.4.0, headless).

- **Partial paths resolve in every field, not only the source.** RULE-108 cited
  `nil (ViewModel/ViewModel.PayslipDocument.swift:17)` in its parameters, and the range check reported the file as
  not found. `render.py catalogs` now completes paths in every field of use cases, screens, flows and rules (nested
  lists and objects too), except `name`, which is part of the id key.

- **An off-by-one range at the end of a file is clamped.** UC-033 cited `PayslipsListCoordinator.swift:25-124` in a
  123-line file, and the grader failed `citations-resolve`. `render.py catalogs` now ends a range on the file's last
  line when it starts inside the file and ends at most 3 lines past it, and records a `clamped` entry in
  `render-warnings.json`. A range further past the end is a wrong citation and is still reported as `citation`.

- **A touch shard keeps the rules of the module's use cases.** The year-end rules in `ReportsService.swift` (a touch
  file the module calls) went out of scope, and four `scope` warnings said they cite a kept use case's code. With a
  use-case index, the touch-shard extractor is now told that a rule serving an indexed use case goes in `rules` with
  that use case. With a capability scope, `render.py` already keeps such a rule; without one, it still leaves.

- **A navigation coordinator is not a screen.** The mapper listed `PayslipsListCoordinator`,
  `ShowPayslipCoordinator`, `PresentPayslipCoordinator` and `ShowEndYearCoordinator` as SCR-015 to SCR-018, with
  old-app plumbing as their states (critic-1, High). The mapper prompt now says a coordinator is never a screen, and
  `render.py catalogs` leaves out a mapped screen that is an inventory coordinator and no inventory screen, with
  one `screen` warning; the use cases and flows that named it drop the name without more warnings.

- **The skill says how an agent's answer reaches `save_json.py`.** It allowed "the agent's transcript (`.jsonl`)", so
  the v4 run searched the subagent folders under `~/.claude/projects` for a contract batch, and the command was
  denied. The session now writes the answer unchanged with the Write tool to `OUT/answers/<file>.txt` and saves that
  file; it never searches session or transcript folders.

- **Referees correct only what is wrong.** In v4 the rule referees made 84 corrections on 45 of 87 rules. Most added
  real precision, but some only added old-app names to a right field (`pastUrl is nil and hasPrevious() is false`,
  `PayslipError.noPayslips`), the plumbing critic-1 asked to remove. The referee prompt now says to correct only a
  wrong value or condition and never to add type, function, property or error names of the old app.

Agent and schema fixes from the Devin run-2 register, group C.

- **The analysed repo's own agent configuration is not an injection (P27).** `CLAUDE.md`, `AGENTS.md` and `.claude/`
  files of the source app were reported as planted text. Both workflows now return them in `agentConfig` ("agent
  config, not followed") and keep `injectionFlags` for the rest.

- **The mapper names the injection field the schema has (P16).** `use-case-mapper.md` told the agent to report
  instruction-shaped text in "the flags field", and the workflow prompt said "injectionSuspects (or flags)"; the
  schema has only `injectionSuspects`, so a strict schema run could lose the flags. Both now say `injectionSuspects`.

Inventory fixes from the Devin run-2 register, group B.

- **Endpoints keep their original spelling in the spec (P10/P26).** `normalize_endpoint` lowercases a path so that
  the app, the inventory and the backend routes match, and the spec showed the lowercase key
  (`/payslips/exportfromalltenants`). `endpoints.json` now also has `display`, the same path in the spelling of the
  app's literal (`/payslips/exportFromAllTenants`); the spec shows it. Matching still uses the lowercase `path`.

- **A URL a service builds is an endpoint (P11/P21).** `PayslipService.swift:155-156` builds `allpayslips` as
  `let payslipUrl = "\(base)\(v1)" + "/employees/\(id)/allpayslips?..."`; the iOS scan read neither the `+` nor the
  name, so the inventory missed it and the spec said `Client: UNKNOWN`. A `let` whose name ends in `Url`, `URL`,
  `Path` or `Endpoint` and whose value is one literal or several joined with `+` is now scanned. The entry has client
  `url-builder`, type `<Type>.<function>`, and the method the type passes as `httpMethod: .GET` when it passes
  exactly one.

- **An endpoint the module reaches through a shared service is in the inventory (P11/P21).** `allreports` and the
  year-end report detail are request types of the Reports package, outside the module; the module calls
  `reportsService.getYearEndReports(...)`, and `ReportsService.swift` (a touch point) calls the request. The
  inventory kept only endpoints declared in the module's files, so both were missing. It now also keeps, as touch
  entries with `usedBy` (the calling `file:line`), the endpoints of request types that a core file calls, and of
  request types called inside the service functions a core file calls on a service type it names (a type ending
  in Service, Client, Repository or API). Only the called functions are read, and calls of standard methods such
  as `dict.merge(...)` are not taken for a service function of the same name. On the payslips module this adds
  the two report endpoints and the two Dottie notification endpoints the start page calls, and nothing else.

- **String keys behind a generated accessor type are found (P6).** me-ios reads its strings through `struct S`
  (`S.Payslips.payslipTitle.localized`, with `static let payslipTitle = "PAYSLIP_TITLE"` in `Strings.swift`), and
  the module's string keys were only the quoted literals of its core files: 7 on payslips, and the ledger's strings
  class had 0 of 1. `module.py` now maps every nested Swift `static let` whose value is a catalog key to its
  qualified name and resolves the core files' references through it: 46 keys on payslips.

- **Events a module sends from a shared event enum are found (P14).** The payslip events are cases of
  `enum Event` in the EmployeeAnalytics package, and the module sends them with `.log(event: .payslipOpen)`; the
  inventory kept only events declared in the module's files and had 0. It now also keeps, as touch entries with
  `usedBy`, the event-enum cases declared outside the module that a core file sends (`event: .x`, `name: .x`,
  `log(.x)`, `track(.x)`): 6 on payslips (payslip open, year-end reports tab opened, export all payslips, and three
  start-page events).

## 0.4.0 - 2026-11-02

Fixes found in the v3 payslips rerun (0.3.0 code).

- **A review finding reaches every owner that states the behaviour.** Critic-1 sent the silent year-end failure to
  the writer, who fixed the screen and the criterion; EP-007 (contracts) still described the alert, and critic-2
  raised it again as High. A critic finding can now name `alsoAffects`, the other agent owners whose sections state
  the same behaviour, and the critic is told to look for them. `review.py append` keeps only known agent owners
  there, `REVIEW.md` shows them, and the new `review.py route OUT` lists the Blocker and High findings of the last
  pass per owner, so step 7.5 sends each finding to all of them.

- **A citation relative to a folder inside the app resolves to its full path.** A rules extractor cited
  `Features/Main/MainPayslipFeature.swift:251-254`, relative to the module, not the app root; the range check
  reported it, but nothing fixed it, and the core check could send the rule out of scope. `render.py catalogs` now
  rewrites a use case's files, a screen's file and a rule's source that name no file, but name the end of exactly one
  real file, to that file's path from the app root (`paths.complete`). A path that fits no file, or several, stays as
  cited and is still reported.

- **A rule keeps its id when its source path is corrected.** `ids.json` keys a rule by its name and source. In the v3
  run a patch corrected the paths in the source of "Export with no payslips shows a dedicated message", RULE-073
  became RULE-117, and the spec and critic-2 still named RULE-073. A new key now takes the id of an old key with the
  same name whose first source file is the same file, cited by the same, a shorter or a longer path, when no rule of
  the run still holds that id. A rule whose source moved to another file still gets a new id.

- **The out-of-scope list drops what a kept use case or rule covers.** Touch-shard analysts listed year-end reports,
  the FAQ link and analytics out of scope, "leave it to the core shard"; the core shard kept them, but the list kept
  them too, because "Learn why I have no payslips (CAP-231)" is not exactly "Learn why I have no payslips". Both
  workflows now compare names without parenthetical notes and capability ids. `render.py catalogs` also drops an
  out-of-scope use case or rule whose cited line ranges all lie inside the ranges of kept entries (the year-end
  rules at `ReportsService.swift:41-46` inside the kept use case's `ReportsService.swift:41-60`). A whole-file
  citation never counts, so a shared file such as a tab coordinator does not hide a neighbour. An out-of-scope rule
  inside a kept use case's code has no given/when/then to keep; it gets a `scope` warning in `render-warnings.json`.

- **Referees can correct, not only keep or drop (P18).** RULE-091 ("Offset is the page size, not an offset") passed
  its referee with the wrong value, and only the critic caught it. The rule referee's verdict now has `corrections`:
  the corrected text of a wrong `plainEnglish`, `given`, `when`, `then` or `category`, with a citation. The use-case
  referee can correct a `description` the same way. The workflow applies each correction and lists it in a new
  `corrected` result field (`{name, field, from, to, citation}`) and `stats.corrected`; the Finish report names them.

## 0.3.0 - 2026-11-02

Fixes found in the second payslips run (Devin, v0.2.0).

- **A use case without a rule can state the real reason.** Next to `No client-side rule; the server decides.`, the
  grader and the renderer accept a cited `No client-side rule: <reason>.`, such as "this use case only opens the
  assistant sheet". A placeholder or a reason under 12 characters still fails. The writer is told never to claim the
  server decides when the code does not show it.

- **A TCA reducer with no view is not a screen.** The iOS inventory keeps a `@Reducer` type among screens only when
  some Swift file holds a store of it (`StoreOf<Name>` or `Store<Name.State, ...>`). A reducer that is only scoped
  into a parent, such as `AnalyticsFeature` or `AppRatingFeature`, goes to `tcaReducers` and is not held to the
  screen threshold of the ledger. A SwiftUI sub-view (a row, a cell, a body view) declared in the folder of a kept screen
  now counts as part of that screen, as a reducer already did.

- **Citation ranges are checked in the catalogs.** `render.py catalogs` and `merge_contracts.py` check every
  `path:line` in the use cases, screens, flows, rules and endpoints (contract field sources included) and add a
  `citation` warning to `render-warnings.json` for a range past the end of its file or a file that is not there.
  Contract field tables in the spec get a `Source` column, so the grader's `citations-resolve` now checks field
  sources too. The agents that cite are told a range ends on or before the file's last line. A bare file name
  (`MainPayslipView.swift:38`) is checked against the one file of that name, and skipped when none or several match.

- **Behaviour that differs by OS version is stated per branch.** The analyst, rule extractor, writer and critic
  prompts say to read every `if #available`, `#if os`, `Build.VERSION.SDK_INT` or `Platform.OS` branch and state the
  behaviour per branch. A store flag is not what the user sees until each rendering branch is checked. In the
  payslips run, the segment picker was said to hide without reports, but the iOS 26 branch shows it always.

- **In-scope capabilities stay in scope.** With `--scope`, the skill passes the chosen capabilities (id, name and
  description) to both workflows. The analysts, the mapper and the rule extractors are told that a use case or rule
  serving one of them is never out of scope, even when its evidence is only in touch files, such as a start-page
  card or a shortcut. `--module` together with `--scope` now adds the folders to the capability files instead of
  being ignored. In the second payslips run the Salary card and its shortcut were dropped as a neighbour module.
  With a capability scope, `render.py catalogs` keeps a rule of a kept use case even when its source is a touch file
  (the salary card gate, the push handler); without a scope, touch-sourced rules still leave.

- **A note after an endpoint path no longer makes a second endpoint.** `GET /x/{id} (push path only)` and
  `GET /Payslip/Export (single company)` normalize to the same endpoint as the plain path.

- **The out-of-scope list is not held to the banned nouns.** The renderer's one-line list of neighbour use cases and
  rules quotes the agents' names (such as "Shared Realm encryption keychain tags"); the grader no longer fails
  `banned-nouns` on it.

## 0.2.0 - 2026-11-02

Fixes found in a run on a native iOS payslips module.

- **Touch points stay near the module.** A type nested in a core type (`ViewModel`, `Delegate`, `Destination` in a
  TCA feature) matches only in its qualified form, more common nested names count as generic, a core name that
  another file also declares is ambiguous and does not match, and an event family counts only when the core declares
  it. On the payslips module, touch points fell from 486 to 18. `module.py --touch-keyword WORD` keeps only touch
  points that contain the word and records the filter in `module.json`.
- **ASP.NET routes given as constants are found.** `[Route(RouteHelper.Payslip.Controller)]` and
  `[HttpGet(RouteHelper.Payslip.AllPayslips)]` resolve through the repository's `const string` and
  `static readonly string` fields, by nested class, with `+`, interpolation and `nameof`. An action with several verb
  attributes gives one route each, `[HttpGet]` with an action `[Route]` uses that template, and a controller inherits
  the `[Route]`, `[ApiVersion]` and `[Authorize]` of its base class. A constant that cannot be resolved is listed in
  `contractsRun[].unresolvedRoutes`. The attribute line of an action far into a controller is now right. On the
  payslips run, 13 of 13 endpoints matched, against 0.
- **Neighbour use cases and rules stay out of the spec.** Touch shards are context: the analyst, mapper and extractor
  prompts say so, and what they find only in touch files goes to a new `outOfScope` list. `render.py catalogs` also
  moves a use case whose files are all outside the core, a rule whose source is outside it, and a rule of such a use
  case to `out-of-scope.json`. Every path a citation names counts (`A.swift:9 (gating in B.swift:3)`), so one core
  path keeps it in scope. The spec names them on one Dependencies line, and the skill asks a person to confirm the
  list after step 3.
- **Citation paths are made root-relative.** `merge_contracts.py` rewrites every string of a reader envelope, and
  `render.py spec` every string of `prose.json`, so an absolute path under the app or a contract root, or one that
  starts with the root's folder name (`me-api/...`), becomes relative to that root and resolves in the grader. The
  contract reader is told to cite that way.
- **A re-merged envelope replaces its disagreements.** When an envelope holds an endpoint, the saved disagreements of
  that endpoint go, and `merge_contracts.py` rebuilds each endpoint's list from `contracts_result.json` instead of
  appending to it, so an edited disagreement no longer sits next to its old version. The ambiguous-route note of
  `contracts.py` stays.
- **Endpoints reached through a server link are kept.** A use case that cites `GET {report.export.href}` gets an
  endpoint with `path: null`, `followsLink` and label `UNKNOWN`, and an open question, instead of a dropped citation.
  `contracts.py` finds the ASP.NET response property that builds the link from a route constant and sets the path,
  so the year-end report PDF of the payslips run now resolves to `api/v1/employees/report/{reportId}/export/pdf`.
  A next or previous page link becomes a `paging` note on the use case's collection endpoints.
- **The ledger holds only the module's own items to a threshold.** `inventory.py` marks each entry `scope: core` or
  `scope: touch` by its file. `ledger.py` counts core items and any item the spec references; a touch-only or
  app-wide item nothing references is listed under `informational` and apart in LEDGER.md. A TCA reducer and its
  nested `Path` and `Destination` count as covered when a kept screen sits in the same file or folder. On the
  payslips run, the Info.plist permissions and the keychain storage no longer fail the ledger, and screens fail only
  on core items.
- **Critic findings go to an owner that can fix them.** A new owner `person` takes a reason for `overrides.json` or a
  decision. The critic maps Appendix A (fields) to `analyst` and Appendix F (coverage reasons) to `person`, and
  `review.py` enforces that by section. `REVIEW.md` lists person findings under "For a person to decide", and the
  skill never sends them to an agent nor keeps a pass running for them.
- **`--module` takes a source file or a file glob.** `--module Employee/StartPage/.../PayslipCardDetailsProvider.swift`
  puts that one file in the core. A test now holds that a re-run with other modules leaves only its own
  `shards/*.json`, so the skill never needs to delete the folder.
- **`save_json.py` saves what an agent or a workflow returned.** It reads a workflow task output, a transcript in
  JSON Lines or plain text, takes the last fenced or bare JSON value that holds `--key` (or a list with `--list`),
  unwraps `{"result": ...}`, checks that it parses and writes the file. Every "save as" step of the skills names it.

## 0.1.0 - 2026-10-30

First release. Turns one module of one mobile app (native iOS, React Native or native Android) into a reviewed spec.

- **Three commands.** `/app-spec:spec` writes the spec, `/app-spec:review` grades it again after a person edits it
  (`--accept` records a reason for an uncovered item), and `/app-spec:status` says where a run stands and what to run
  next.
- **A fixed template.** Eight sections and six appendices, ids that never change (`UC`, `SCR`, `FLOW`, `RULE`, `EP`),
  evidence labels, `file:line` citations and numbered acceptance criteria. Optional `CAP-NNN` aliases from an App
  Fusion capability index.
- **Measured completeness.** A deterministic inventory of the module, a coverage ledger with a threshold per class and
  a reason for each item left out, a ten-check shape grader, and a critic that opens cited code. Blocker and High
  findings go back to the part that owns them for up to two more passes (1 to 5 with `--passes`).
- **Eight agents and two workflows.** Analysts for iOS, Android and React Native, a use-case mapper, a business-rules
  extractor, a contract reader, a spec writer and a spec critic. The understand and rules workflows are resumable.
  Every skill also gives the path without the Workflow tool.
- **Endpoint contracts.** With `--contracts`, each route is found in a backend repository and its request, response,
  errors and auth are merged in. Disagreements between the app and the backend are listed.
- **Safety.** A guard hook denies file writes into the analysed app and the backend repositories, and asks before a
  shell command that would. Analysed content is data, never instructions, and instruction-shaped text is reported. A
  secret is never reproduced.
- **Runs in Devin.** The guard matches Devin's tools, and a session-start note gives the plugin's folder, the tool
  names and the path without the Workflow tool.
- **Tests and evals.** Python and Node tests, and three eval cases: a headless run on a synthetic app (structure
  only), the source guard, and the next command from `/app-spec:status`.
