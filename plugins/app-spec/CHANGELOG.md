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
