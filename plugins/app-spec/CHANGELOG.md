# Changelog

A release gets a new number in `.claude-plugin/plugin.json`. Claude Code only offers an update when that number
changes.

## Unreleased

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
