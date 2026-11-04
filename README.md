# app-spec

Point a command at one module of one mobile app (native iOS, React Native or native Android) and get a reviewed
spec, in a fixed template, that is deep enough to plan and build the same feature in a new app.

The plugin lives in [`plugins/app-spec`](plugins/app-spec). Its contract is
[`plugins/app-spec/docs/DESIGN.md`](plugins/app-spec/docs/DESIGN.md). The approved design is
[`docs/superpowers/specs/2026-10-30-app-spec-design.md`](docs/superpowers/specs/2026-10-30-app-spec-design.md).

## What you get

A spec of the module in a fixed template, with numbered acceptance criteria, a coverage ledger that lists every item
not covered with a reason, and a critic's review. The analysed app is never written to. See the
[plugin README](plugins/app-spec/README.md) for the path, how completeness is measured, and safety.

## Status

Release 0.9.0 (November 2026). On the acceptance module (me-ios payslips, 13,000 lines) a headless run with three
review passes takes about 90 minutes and writes a 2,300-line spec with 68 acceptance criteria and 865 code citations;
the grade passes, no step is done by hand, and the last pass leaves no Blocker. See
[`docs/HANDOVER.md`](docs/HANDOVER.md) for the scorecard of every run and what is open.

## Install

Claude Code:

```
/plugin marketplace add danchily2/app-spec
/plugin install app-spec@app-spec
```

Claude Code, from a local clone:

```
claude --plugin-dir plugins/app-spec
```

Devin:

```
devin plugins install danchily2/app-spec#plugins/app-spec
```

## Licence

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
