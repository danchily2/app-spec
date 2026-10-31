# Changelog

A release gets a new number in `.claude-plugin/plugin.json`. Claude Code only offers an update when that number
changes.

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
