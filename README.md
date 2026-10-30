# app-spec

Point a command at one module of one mobile app (native iOS, React Native or native Android) and get a reviewed
spec, in a fixed template, that is deep enough to plan and build the same feature in a new app.

The plugin lives in [`plugins/app-spec`](plugins/app-spec). Its contract is
[`plugins/app-spec/docs/DESIGN.md`](plugins/app-spec/docs/DESIGN.md). The approved design is
[`docs/superpowers/specs/2026-10-30-app-spec-design.md`](docs/superpowers/specs/2026-10-30-app-spec-design.md).

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
