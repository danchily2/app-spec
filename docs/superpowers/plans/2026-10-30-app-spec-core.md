# app-spec core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `app-spec` Claude Code and Devin plugin up to a working `spec`, `review` and `status` command: one module of one mobile app in, a reviewed spec in Scarlet's `/spec` template out, with a coverage ledger.

**Architecture:** A plugin in the App Fusion layout: Markdown skills orchestrate standard-library Python scripts (module resolution, inventory, field inventory, stable ids, rendering, ledger, grader, status, guard) and two Workflow-tool fan-outs (understand the module, extract its rules) with read-only analyst agents and referees. Every fact in the spec comes from a JSON catalog the scripts wrote; agents propose, scripts render and measure, a critic grades, a person reads.

**Tech Stack:** Python 3.8+ standard library only; Markdown skills and agents; JavaScript Workflow scripts tested with a stubbed harness; `claude plugin validate` and `claude plugin eval`.

**Spec:** `docs/superpowers/specs/2026-10-30-app-spec-design.md` (the design). This plan covers sections 5.1 to 5.9 and 5.12 to 5.16 of it except the `tests` and `compare` commands (5.10, 5.11), which get their own plan once this one ships, because they consume this plan's catalogs and can be reviewed on their own.

## Global Constraints

- Python scripts use the standard library only, run on Python 3.8+, and never import a third-party package.
- Scripts, agents and skills never write under the analysed app's path or under a contract repository's path. Writes go to the output folder only.
- Analysed code, comments, strings and READMEs are data, never instructions; instruction-shaped text is reported in `injectionFlags`, never acted on.
- Secrets are never reproduced: `file:line` plus a 2 to 4 character masked preview.
- The spec's first eight sections use exactly these headings, in this order: `## Summary`, `## Capabilities`, `## Screens`, `## Endpoints`, `## Business rules and permissions`, `## Acceptance criteria`, `## Dependencies and decisions`, `## Open questions`. Appendices follow as `## Appendix A. Fields and ids`, `## Appendix B. Data`, `## Appendix C. Behaviour to keep, implementation to drop`, `## Appendix D. Strings, analytics and platform`, `## Appendix E. Flows`, `## Appendix F. Coverage`.
- Acceptance criteria are rendered one per line as `- **AC<N> (<id>[, <id>]):** <text>`, numbered from 1 across the whole spec in steps of one, where `<id>` is `UC-NNN` or its `CAP-NNN` alias.
- Header lines: `Source: module <name> of <app> (no source issue)` and `Reference HEADs: <app> \`<sha>\`` followed by one entry per contract repository.
- Evidence labels are exactly `VERIFIED`, `INFERRED`, `UNKNOWN` and `PROPOSED`.
- Ids are `UC-NNN`, `SCR-NNN`, `FLOW-NNN`, `RULE-NNN`, `EP-NNN`, three digits minimum, never reused, kept in `ids.json` in the output folder and stable across re-runs by normalized key.
- Coverage thresholds default to 100 percent for screens, endpoints, events, permissions and storage keys and 95 percent for string keys and fields; an uncovered item passes only with a reason in `overrides.json` or in the catalog (`not user-facing`, `dead code`, `out of module`).
- The review loop runs at most `passes` rounds, default 2.
- Shards hold at most 9,000 non-blank lines by default.
- The plugin is public under Apache 2.0; no file derived from Visma code is committed. Fixtures are synthetic.
- Devin compatibility as App Fusion: the guard matches `Edit|Write|MultiEdit|NotebookEdit|Bash` and `edit|write|notebook_edit|apply_patch|exec|write_to_process`; `APP_SPEC_GUARD=false` turns it off in Devin; a session-start note prints the plugin's real folder and the tool-name mapping only when `DEVIN_PLUGIN_ROOT` or `DEVIN_PROJECT_DIR` is set.

## Review Focus

1. A module name that matches no folder, or several, must stop with the candidates listed, never pick one silently. Test in Task 3.
2. An endpoint path or string key the code builds dynamically must stay unresolved (`{}` in the path, `textKey: null`) and be labelled UNKNOWN, never invented. Tests in Task 5.
3. A citation whose line range is beyond the file's length (a re-run on a moved commit) must fail the grader with the citation listed. Test in Task 13.
4. An `overrides.json` entry that names an id no catalog has any more must be reported as drift, never dropped. Test in Task 13.
5. A module larger than one shard (the calendar module is 40,767 lines) must be split so no shard exceeds the limit and no file is lost. Test in Task 3.

---

## File structure

```
app-spec/                                   the repository (exists; holds the design)
  .claude-plugin/marketplace.json           one plugin: ./plugins/app-spec
  .devin-plugin/plugin.json                 Devin meta-plugin requiring plugins/app-spec
  LICENSE  NOTICE  README.md  .gitignore
  docs/superpowers/specs/, docs/superpowers/plans/
  plugins/app-spec/
    .claude-plugin/plugin.json              name app-spec, version 0.1.0, userConfig guard + passes
    README.md  CHANGELOG.md  LICENSE  NOTICE
    docs/DESIGN.md                          the contract: output folder, JSON schemas, ids, template, thresholds
    skills/spec/SKILL.md  skills/review/SKILL.md  skills/status/SKILL.md
    agents/ios-analyst.md  android-analyst.md  rn-analyst.md          (App Fusion, unchanged)
    agents/business-rules-extractor.md                                 (App Fusion, unchanged)
    agents/use-case-mapper.md  contract-reader.md  spec-writer.md  spec-critic.md
    workflows/understand-module.js  workflows/extract-rules.js
    hooks/hooks.json  hooks/guard.sh  hooks/devin-context.sh
    references/rubric.md                    the distilled bar
    scripts/
      speclib/__init__.py common.py detect.py ios.py android.py rn.py strings.py   copied from App Fusion's fusionlib
      speclib/out.py                        output-folder helpers
      speclib/ids.py                        stable id registry
      speclib/touchpoints.py                touch-point discovery
      speclib/fields.py                     field inventory per stack
      speclib/template.py                   headings, appendix names, AC regex
      module.py  inventory.py  render.py  contracts.py  ledger.py  grade.py  status.py  guard.py  devin_context.py
      tests/helpers.py  tests/fixtures/{ios-app,android-app,rn-app,backend-aspnet,backend-express}/
      tests/test_*.py
    tests/harness.mjs  tests/workflows.test.mjs
    evals/_fixtures/make-apps.sh  evals/spec-fixture/  evals/source-guard/  evals/status-next/
```

Output folder contract (what every script reads and writes), fixed in `docs/DESIGN.md` by Task 1:

```
<out>/
  app-spec.json   {"version":1,"app":{"path","name","stack","commit","branch","clean"},
                   "module":{"query":[...],"confirmed":bool},
                   "contracts":[{"path","name","commit"}],
                   "capabilityIndex": path|null, "scope":[CAP ids]|null,
                   "options":{"passes":2,"locale":"en",
                              "thresholds":{"screens":100,"endpoints":100,"events":100,"permissions":100,"storage":100,"strings":95,"fields":95},
                              "bannedNouns":["Realm","Swinject","NotificationCenter","ViewModel","Redux","Hilt","Room"]},
                   "created": ISO}
  overrides.json  {"version":1,"drop":[{"kind":"field|screen|useCase|endpoint|string|event","id":"...","reason":"..."}],
                   "rename":[{"id":"...","name":"..."}],"ids":{"SCR-001.title":"pay.list.title"},
                   "merge":[{"into":"UC-003","from":["UC-007"]}]}
  module.json     {"version":1,"core":[rel],"touchPoints":[{"file":rel,"reason":str}],"stringKeys":[str],
                   "shards":[{"id","kind":"core|touch","name","files":[rel],"loc":int,"file":"shards/<id>.json"}],"loc":int}
  shards/<id>.json
  inventory.json, INVENTORY.md                 App Fusion's inventory shape, scoped to module.json files
  fields.json     {"version":1,"screens":[{"screen":str,"file":"rel:line",
                   "elements":[{"kind":"text|input|button|toggle|picker|list|image|document|other",
                                "textKey":str|null,"text":str|null,"identifier":str|null,"file":rel,"line":int}]}]}
  understand_result.json, rules_result.json    the workflows' results, as returned
  ids.json        {"UC":{"<normalized key>":"UC-001",...},"SCR":{...},"FLOW":{...},"RULE":{...},"EP":{...},"max":{"UC":7,...}}
  use-cases.json  {"version":1,"useCases":[{"id","alias":CAP|null,"name","description","personas","permissions",
                   "screens":[SCR ids],"files","endpoints":[EP ids],"events","strings","storage","platform","evidence"}]}
  screens.json    {"screens":[{"id","name","file","useCases":[UC ids],"actions":[str],"states":[{"name","shows":str,"evidence"}],
                   "elements":[fields.json elements + "proposedId"]}]}
  flows.json      {"flows":[{"id","name","persona","steps":[{"screen":SCR,"useCases":[UC],"action":str}]}]}
  rules.json      {"rules":[{"id","useCase":UC|null,"name","category","priority","confidence","plainEnglish","given","when","then",
                   "parameters","edgeCases","suspectedDefect","question","source"}]}
  endpoints.json  {"endpoints":[{"id","method","path","raw","useCases":[UC],"client":{"file","type"},
                   "request":{"fields":[{"name","type","required"}]},"response":{"fields":[...]},"errors":[{"status","reaction"}],
                   "auth":str|null,"backend":{"repo","file","line","auth"}|null,"label":"VERIFIED|INFERRED|UNKNOWN"}]}
  ledger.json, LEDGER.md    {"version":1,"classes":{"<class>":{"total","covered","uncovered":[{"item","reason"|null}]}},
                             "thresholds":{...},"pass":bool}
  grade.json      {"version":1,"checks":[{"name","pass","detail"}],"pass":bool}
  review.json, REVIEW.md    {"passes":[{"n","ledger":{"pass"},"grade":{"pass"},"critic":[{"severity","section","finding","fix","owner"}]}]}
  SPEC.md (or --name)
  OPEN_QUESTIONS.md
```

---

### Task 1: Repository skeleton, plugin manifests and the design contract

**Files:**
- Create: `.claude-plugin/marketplace.json`, `.devin-plugin/plugin.json`, `LICENSE`, `NOTICE`, `README.md`, `.gitignore`
- Create: `plugins/app-spec/.claude-plugin/plugin.json`, `plugins/app-spec/README.md`, `plugins/app-spec/CHANGELOG.md`, `plugins/app-spec/LICENSE`, `plugins/app-spec/NOTICE`
- Create: `plugins/app-spec/docs/DESIGN.md`

**Interfaces:**
- Produces: `docs/DESIGN.md`, the contract every later task codes against: the output folder layout and every JSON shape from the File structure above, the ids rule, the template headings and AC line format from Global Constraints, the thresholds and the banned-nouns default. Later tasks cite its section names; they never redefine a shape.

- [ ] **Step 1: Write the manifests.** `marketplace.json`: name `app-spec`, owner Dan-Mihai Cuc, one plugin `app-spec` at `./plugins/app-spec`, version `0.1.0`, category `development`, tags `mobile, ios, android, react-native, spec, migration`. `.devin-plugin/plugin.json`: name `app-spec-marketplace`, `requiredPlugins` with `source: git-subdir`, url `https://github.com/danchily2/app-spec.git`, path `plugins/app-spec`. `plugins/app-spec/.claude-plugin/plugin.json`: name `app-spec`, displayName `App Spec`, version `0.1.0`, one-paragraph description from the design's section 1, author, licence `Apache-2.0`, `userConfig` with `guard` (boolean, default true) and `passes` (number, default 2, min 1, max 5).

- [ ] **Step 2: Write `docs/DESIGN.md`** with these sections: Purpose (three sentences from the design), Words (module, core, touch point, use case, screen, flow, rule, endpoint, override), Output folder (the tree and every JSON shape, copied from this plan's File structure, each field with one line of meaning), Ids, Template (headings, appendix names, header lines, AC line format), Thresholds and defaults, Agents and workflows (names and what each returns), Hooks, Safety (read-only source, untrusted content, secrets).

- [ ] **Step 3: Licence files and README stubs.** Apache 2.0 text in `LICENSE`; `NOTICE` naming App Fusion as the origin of the copied scripts and agents; root `README.md` with install lines (`/plugin marketplace add`, `/plugin install app-spec@app-spec`, `claude --plugin-dir`, `devin plugins install danchily2/app-spec#plugins/app-spec`) and a pointer to the design; `.gitignore` with `__pycache__/`, `*.pyc`, `node_modules/`, `.DS_Store`.

- [ ] **Step 4: Validate**

Run: `claude plugin validate plugins/app-spec`
Expected: validation passes with no error for the manifest (skills, agents and hooks are added by later tasks).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: plugin skeleton, manifests and the design contract"
```

---

### Task 2: speclib from App Fusion's fusionlib, and the fixture apps

**Files:**
- Create: `plugins/app-spec/scripts/speclib/__init__.py`, `common.py`, `detect.py`, `ios.py`, `android.py`, `rn.py`, `strings.py` (copied from `app-fusion/plugins/app-fusion/scripts/fusionlib/`), `out.py`
- Create: `plugins/app-spec/scripts/tests/helpers.py`, `plugins/app-spec/scripts/tests/fixtures/ios-app/**`, `android-app/**`, `rn-app/**`
- Test: `plugins/app-spec/scripts/tests/test_speclib.py`

**Interfaces:**
- Consumes: App Fusion's `detect.detect(root) -> {"stack": "ios-native"|"android-native"|"react-native"|"other", ...}`, `ios.extract(root) -> dict`, `android.extract(root) -> dict`, `rn.extract(root) -> dict`, `strings.find_i18n_json/parse_xcstrings/parse_android_strings/combine/summary`, `common.walk/read_text/normalize_endpoint/endpoints_match/git_info/write_json/write_text/load_json/md_table/mask/looks_secret`.
- Produces: `speclib.out.load_config(out: str) -> dict` (reads `app-spec.json`, exits 2 with "not an app-spec output folder" when missing); `out.load(out, name, default=None) -> Any`; `out.save(out, name, data) -> str` (JSON with two-space indent, UTF-8, trailing newline, returns the path); `out.save_text(out, name, text) -> str`; `out.rel(app_root, path) -> str`; `out.app_root(cfg) -> str`. The fixture apps: `ios-app` (a `Package.swift`, `Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift` with three SwiftUI elements and one `.accessibilityIdentifier("pay.list.title")`, `PayslipDetailView.swift` with four elements including an icon-only `Button` with `Image(systemName:)`, `EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift` with a request type whose path is `"\(APIConstants.URL.v1)/employees/\(id)/payslips"` and a constants file resolving `v1` to `/employee/api/v1`, `GetPayslipPdf.swift` whose path appends a runtime `document.url` value so it cannot be resolved, `Resources/Localizable.xcstrings` with six keys of which three contain `payslip`, `Employee/StartPage/PayslipCard.swift` referencing `PayslipItem` and the key `payslip.latest`, an analytics enum `PayslipEvent` with two cases, and `Modules/CalendarFeature/...` with one unrelated view), `android-app` (a Gradle module with one Compose screen using `Modifier.testTag("pay.list.title")`, `stringResource(R.string.payslip_title)`, a Retrofit interface with `@GET("employee/api/v1/employees/{id}/payslips")`, `res/values/strings.xml`), `rn-app` (one screen with `testID="pay.list.title"`, `t('payslip.title')`, an axios call to `` `${BASE}/employees/${id}/payslips` ``). Each fixture is synthetic and under 300 lines in all.

- [ ] **Step 1: Write the failing tests**

```python
class TestSpeclib(unittest.TestCase):
    def test_detect_fixture_stacks(self):
        self.assertEqual(detect.detect(FIX / "ios-app")["stack"], "ios-native")
        self.assertEqual(detect.detect(FIX / "android-app")["stack"], "android-native")
        self.assertEqual(detect.detect(FIX / "rn-app")["stack"], "react-native")
    def test_ios_extract_resolves_endpoint_constant(self):
        inv = ios.extract(str(FIX / "ios-app"))
        self.assertIn(("GET", "/employee/api/v1/employees/{}/payslips"), {(e["method"], e["path"]) for e in inv["endpoints"]})
    def test_out_roundtrip(self):
        out.save(tmp, "x.json", {"a": 1}); self.assertEqual(out.load(tmp, "x.json"), {"a": 1})
    def test_load_config_missing_exits(self):
        with self.assertRaises(SystemExit): out.load_config(tmp_without_config)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s plugins/app-spec/scripts/tests -v`
Expected: FAIL with `ModuleNotFoundError: speclib`.

- [ ] **Step 3: Copy fusionlib into `speclib/` and adapt.** Remove from `common.py` every function that needs a program or workspace: `workspace`, `program_dir`, `app_dir`, `legacy_dir`, `load_program`, `find_programs`. Fix `from fusionlib import ...` to `from speclib import ...`. Keep `detect.py`, `ios.py`, `android.py`, `rn.py`, `strings.py` unchanged apart from imports. Write `out.py` with the signatures above. Build the three fixture apps as described, by hand, synthetic.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s plugins/app-spec/scripts/tests -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(scripts): speclib from App Fusion's extractors, output helpers, synthetic fixture apps"
```

---

### Task 3: `module.py`: resolve a module, find its touch points, shard it

**Files:**
- Create: `plugins/app-spec/scripts/module.py`, `plugins/app-spec/scripts/speclib/touchpoints.py`
- Test: `plugins/app-spec/scripts/tests/test_module.py`

**Interfaces:**
- Consumes: `speclib.detect.detect`, `speclib.common.walk/read_text/git_info/loc_by_language`, `speclib.strings` catalog functions, `speclib.out`.
- Produces: `module.resolve_by_name(app_root: str, stack: str, names: list[str]) -> dict` returning `{"core": [rel folders], "candidates": [{"folder": rel, "files": int, "loc": int}]}`, where `core` is the folders whose last path component contains a name case-insensitively among package roots (`Package.swift` directories, Gradle modules, `src/screens/<x>` and `src/features/<x>`); `module.resolve_by_paths(app_root, paths) -> dict` for explicit folders or globs; `touchpoints.find(app_root: str, stack: str, core_files: list[str], string_keys: list[str]) -> list[{"file": rel, "reason": str}]` where reasons are one of `uses type <T>`, `uses request <R>`, `uses string key <k>`, `routes into <screen>`, `fires event family <F>`; `module.string_keys_for(core_files, catalog) -> list[str]`; `module.make_shards(app_root: str, files: list[str], kind: str, max_lines: int = 9000) -> list[shard]` (adapted from App Fusion's `shard.py` `_split` and `_pack`: group by top folder, split by sub-folder above the limit, merge groups under 300 lines, ids `<kind>-<slug>`); the CLI `module.py <app> --module <name|path> [--module ...] --out DIR [--name NAME] [--contracts REPO ...] [--max-lines N] [--confirmed] [--locale CODE]` which writes `app-spec.json`, `module.json` and `shards/<id>.json`, prints the proposal (core folders with counts, touch points with reasons, string-key count, shard count), and exits 2 with `no folder matches <name>` or `several folders match <name>: ...` when the name is ambiguous and no `--module` path disambiguates.

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_payslips_core_folders(self):
    r = module.resolve_by_name(IOS, "ios-native", ["Payslips"])
    self.assertEqual(sorted(r["core"]), ["EmployeeServices/Payslips", "Modules/PayslipsFeature"])
def test_resolve_unknown_name_has_no_core(self):
    self.assertEqual(module.resolve_by_name(IOS, "ios-native", ["Nothing"])["core"], [])
def test_touch_point_start_page_card(self):
    tps = touchpoints.find(IOS, "ios-native", core_files(IOS), ["payslip.latest"])
    self.assertIn({"file": "Employee/StartPage/PayslipCard.swift", "reason": "uses type PayslipItem"}, tps)
def test_string_keys_for_core(self):
    self.assertEqual(sorted(module.string_keys_for(core_files(IOS), catalog(IOS))), ["payslip.latest", "payslip.list.title", "payslip.pdf"])
def test_shards_respect_max_lines_and_lose_no_file(self):
    shards = module.make_shards(IOS, big_file_list, "core", max_lines=120)
    self.assertTrue(all(s["loc"] <= 120 for s in shards))
    self.assertEqual(sorted(f for s in shards for f in s["files"]), sorted(big_file_list))
def test_cli_writes_config_and_module(self):
    rc = run_cli(["module.py", IOS, "--module", "Payslips", "--out", tmp])
    self.assertEqual(rc, 0)
    cfg = out.load_config(tmp); self.assertFalse(cfg["module"]["confirmed"]); self.assertEqual(cfg["app"]["stack"], "ios-native")
    self.assertTrue((Path(tmp) / "module.json").exists())
def test_cli_ambiguous_name_exits_2(self):
    self.assertEqual(run_cli(["module.py", IOS, "--module", "Feature", "--out", tmp]), 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest plugins/app-spec/scripts/tests/test_module.py -v`
Expected: FAIL with `ModuleNotFoundError: module` or `touchpoints`.

- [ ] **Step 3: Implement `speclib/touchpoints.py` and `module.py`** with the signatures above. Touch points: collect the type and request names the core declares (`struct|class|enum|protocol <Name>` in Swift, `class|data class|interface <Name>` in Kotlin, exported symbols in TypeScript) and grep the rest of the app for them; do the same for the core's string keys and event family names; for routes, find navigation entries (coordinator `push`/`present` of a core screen type, `NavigationLink`/`navigate(` to a core route, tab items) outside the core. One reason per file, the first match wins in the order listed in the Interfaces.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest plugins/app-spec/scripts/tests/test_module.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(module): resolve a module by name or path, find touch points, shard it"
```

---

### Task 4: scope by capability ids through a fusion index

**Files:**
- Modify: `plugins/app-spec/scripts/module.py`
- Test: `plugins/app-spec/scripts/tests/test_module.py`, fixture `plugins/app-spec/scripts/tests/fixtures/capability_index.json`

**Interfaces:**
- Produces: `module.scope_from_index(index_path: str, scope_ids: list[str], app_name: str) -> list[str]` returning the union of `implementations[app_name].files` of the named capabilities, relative to the app root, in a stable order; exits 2 with `unknown capability <id>` or `app <name> has no implementation of <id>` as appropriate. The CLI gains `--capabilities FILE --scope CAP-001,CAP-002`, and the scope's files become the core (folders are the files' parent folders) before touch points are found. `app-spec.json` records `capabilityIndex` and `scope`.

- [ ] **Step 1: Write the failing tests**

```python
def test_scope_from_index_unions_files(self):
    files = module.scope_from_index(INDEX, ["CAP-001", "CAP-002"], "ios-app")
    self.assertEqual(files, ["Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift", "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift"])
def test_scope_unknown_capability_exits(self):
    with self.assertRaises(SystemExit): module.scope_from_index(INDEX, ["CAP-999"], "ios-app")
def test_cli_scope_records_index(self):
    run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-001", "--out", tmp])
    self.assertEqual(out.load_config(tmp)["scope"], ["CAP-001"])
```

The fixture index holds two capabilities for app `ios-app` with the files above and one for another app.

- [ ] **Step 2: Run the tests to verify they fail** (`AttributeError: scope_from_index`).
- [ ] **Step 3: Implement** `scope_from_index` and the CLI flags.
- [ ] **Step 4: Run the tests to verify they pass.**
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(module): scope a run by capability ids through a fusion index"
```

---

### Task 5: `inventory.py` scoped to the module, and the field inventory

**Files:**
- Create: `plugins/app-spec/scripts/inventory.py`, `plugins/app-spec/scripts/speclib/fields.py`
- Test: `plugins/app-spec/scripts/tests/test_inventory.py`, `plugins/app-spec/scripts/tests/test_fields.py`

**Interfaces:**
- Consumes: `module.json` and `app-spec.json` from Task 3; the stack extractors from Task 2.
- Produces: `inventory.run(out: str) -> dict` that runs the stack's `extract(app_root)` and keeps only entries whose `file` is inside `module.json`'s `core` plus `touchPoints`, writes `inventory.json` (App Fusion's shape: `screens, routes, endpoints, events, strings, storage, platform, counts, rules`) and `INVENTORY.md` (every count with its rule); `fields.extract(stack: str, app_root: str, files: list[str]) -> list[screen]` in the `fields.json` shape of the contract, with `kind` from this mapping: SwiftUI `Text`→`text`, `TextField`/`SecureField`→`input`, `Button`→`button`, `Toggle`→`toggle`, `Picker`/`DatePicker`→`picker`, `List`/`ForEach`→`list`, `Image`/`AsyncImage`→`image`, `QuickLookPreview`/`PDFKitView`→`document`; UIKit `UILabel`→`text`, `UITextField`/`UITextView`→`input`, `UIButton`→`button`, `UISwitch`→`toggle`, `UIPickerView`/`UIDatePicker`→`picker`, `UITableView`/`UICollectionView`→`list`, `UIImageView`→`image`; Compose `Text`, `TextField`/`OutlinedTextField`, `Button`/`IconButton`/`TextButton`, `Switch`/`Checkbox`, `DropdownMenu`, `LazyColumn`/`LazyRow`, `Image`/`Icon`; React Native `<Text`, `<TextInput`, `<Button`/`<Pressable`/`<TouchableOpacity`, `<Switch`, `<Picker`, `<FlatList`/`<SectionList`, `<Image`. `identifier` from `.accessibilityIdentifier("x")`, `accessibilityIdentifier = "x"`, `Modifier.testTag("x")`, `testID="x"` within the same statement (up to the next blank line or semicolon); `textKey` from `L10n.<key>`, `String(localized: "<key>")`, `NSLocalizedString("<key>"`, `Strings.<key>`, `stringResource(R.string.<key>)`, `t('<key>')`, `t("<key>")`; `text` the literal when a literal is passed; both `null` when neither resolves. The screen is the file's top-level `View`, `UIViewController`, `@Composable` function whose name ends in `Screen` or `View`, or the default export.

- [ ] **Step 1: Write the failing tests**

```python
def test_inventory_is_scoped_to_module(self):
    inv = inventory.run(OUT_WITH_MODULE)
    self.assertTrue(all(e["file"].startswith(("Modules/PayslipsFeature", "EmployeeServices/Payslips", "Employee/StartPage")) for e in inv["endpoints"] + inv["screens"]))
    self.assertNotIn("CalendarFeature", json.dumps(inv))
def test_inventory_keeps_unresolved_path_template(self):
    inv = inventory.run(OUT_WITH_MODULE)
    e = next(x for x in inv["endpoints"] if x["type"] == "GetPayslipPdf")   # fixture builds its path from a runtime value
    self.assertIn("{}", e["path"]); self.assertTrue(e["raw"])
def test_fields_swiftui_list_screen(self):
    s = next(x for x in fields.extract("ios-native", IOS, core_files(IOS)) if x["screen"] == "PayslipListView")
    kinds = [e["kind"] for e in s["elements"]]; self.assertEqual(kinds, ["text", "list", "button"])
    self.assertEqual(s["elements"][0]["identifier"], "pay.list.title"); self.assertEqual(s["elements"][0]["textKey"], "payslip.list.title")
def test_fields_icon_only_button_has_no_text(self):
    s = next(x for x in fields.extract("ios-native", IOS, core_files(IOS)) if x["screen"] == "PayslipDetailView")
    icon = next(e for e in s["elements"] if e["kind"] == "button" and e["identifier"] is None)
    self.assertIsNone(icon["textKey"]); self.assertIsNone(icon["text"])
def test_fields_compose_test_tag_and_string_resource(self):
    s = fields.extract("android-native", ANDROID, all_files(ANDROID))[0]
    self.assertEqual(s["elements"][0]["identifier"], "pay.list.title"); self.assertEqual(s["elements"][0]["textKey"], "payslip_title")
def test_fields_rn_test_id(self):
    s = fields.extract("react-native", RN, all_files(RN))[0]
    self.assertEqual(s["elements"][0]["identifier"], "pay.list.title"); self.assertEqual(s["elements"][0]["textKey"], "payslip.title")
```

- [ ] **Step 2: Run the tests to verify they fail** (`ModuleNotFoundError`).
- [ ] **Step 3: Implement `inventory.py` and `speclib/fields.py`.** The CLI is `inventory.py <out>`; it prints the counts with their rules and the number of screens and elements in `fields.json`.
- [ ] **Step 4: Run the tests to verify they pass** (6 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(inventory): module-scoped inventory and the field inventory per stack"
```

---

### Task 6: stable ids and the catalogs render

**Files:**
- Create: `plugins/app-spec/scripts/speclib/ids.py`, `plugins/app-spec/scripts/render.py`
- Test: `plugins/app-spec/scripts/tests/test_ids.py`, `plugins/app-spec/scripts/tests/test_render_catalogs.py`, fixtures `tests/fixtures/results/understand_result.json`, `rules_result.json`

**Interfaces:**
- Consumes: `understand_result.json` and `rules_result.json` in the shapes `docs/DESIGN.md` fixes (the workflows of Tasks 8 and 9 return them); `fields.json`, `inventory.json`, `app-spec.json`, optional capability index.
- Produces: `ids.Registry(path: str)` with `assign(prefix: str, key: str) -> str` (returns the existing id for a key, else the next id after the highest ever issued for that prefix, never reusing), `save()`; `ids.norm(text: str) -> str` (lowercase, letters and digits only, articles dropped); `render.catalogs(out: str) -> dict` writing `use-cases.json` (key: `norm(name)`; alias: the `CAP-NNN` whose `norm(name)` equals the use case's or whose implementation files for this app intersect the use case's files), `screens.json` (key: `norm(name)` plus file; elements copied from `fields.json` by screen file, `proposedId` as `<module>.<screen-slug>.<element-slug>` when `identifier` is null), `flows.json`, `rules.json` (key: `norm(name)` plus source file), `endpoints.json` (key: `method + normalized path`; one entry per inventory endpoint in scope, `useCases` from the use cases that cite the endpoint, `label` `VERIFIED` when the client file is cited, `UNKNOWN` when the path still holds `{}` with no resolvable raw); applies `overrides.json` `merge` and `rename`; CLI `render.py catalogs <out>`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ids_are_stable_and_never_reused(self):
    r = ids.Registry(path); a = r.assign("UC", "view payslip"); b = r.assign("UC", "download pdf"); r.save()
    r2 = ids.Registry(path); self.assertEqual(r2.assign("UC", "view payslip"), a)
    self.assertEqual(r2.assign("UC", "new thing"), "UC-003"); self.assertNotEqual(r2.assign("UC", "new thing"), b)
def test_catalogs_rerun_keeps_ids(self):
    render.catalogs(OUT); first = out.load(OUT, "use-cases.json")
    render.catalogs(OUT); self.assertEqual(out.load(OUT, "use-cases.json"), first)
def test_catalog_alias_from_index(self):
    render.catalogs(OUT_WITH_INDEX)
    uc = next(u for u in out.load(OUT_WITH_INDEX, "use-cases.json")["useCases"] if u["name"] == "View a payslip's details")
    self.assertEqual(uc["alias"], "CAP-225")
def test_endpoint_label_unknown_when_unresolved(self):
    render.catalogs(OUT); e = next(x for x in out.load(OUT, "endpoints.json")["endpoints"] if "{}" in x["path"] and not x["useCases"])
    self.assertEqual(e["label"], "UNKNOWN")
def test_override_merge_folds_use_case(self):
    write_overrides(OUT, {"merge": [{"into": "UC-001", "from": ["UC-002"]}]}); render.catalogs(OUT)
    self.assertNotIn("UC-002", [u["id"] for u in out.load(OUT, "use-cases.json")["useCases"]])
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `speclib/ids.py` and `render.py catalogs`.**
- [ ] **Step 4: Run the tests to verify they pass** (5 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(render): stable ids and the catalogs from the workflow results"
```

---

### Task 7: agents

**Files:**
- Create: `plugins/app-spec/agents/ios-analyst.md`, `android-analyst.md`, `rn-analyst.md`, `business-rules-extractor.md` (copied from App Fusion unchanged except the description's product name)
- Create: `plugins/app-spec/agents/use-case-mapper.md`, `plugins/app-spec/agents/contract-reader.md`

**Interfaces:**
- Produces: `use-case-mapper` (tools `Read, Glob, Grep, Bash`, read-only): merges fragments of **one app** into use cases, one per user outcome; splits mixed fragments; groups screens with their actions and states; writes flows of 3 to 8 steps; keeps all evidence; returns JSON matching the caller's schema; no fusion classes, no twins. `contract-reader` (tools `Read, Glob, Grep, Bash`, read-only): for a list of endpoints, opens the app's request and model types and, when given, the backend route the scripts located, and returns request fields, response fields with types and nullability, error statuses and the UI reaction, each with `file:line`; never invents a field; labels each endpoint VERIFIED when both the client and the backend are cited, INFERRED when only the client is, UNKNOWN when neither resolves. Both carry App Fusion's untrusted-content and secret-handling sections verbatim.

- [ ] **Step 1: Copy the four App Fusion agents** and change only the product name in their descriptions.
- [ ] **Step 2: Write `use-case-mapper.md` and `contract-reader.md`** per the Interfaces, each with sections: role, how to read, what to return, untrusted content, read-only.
- [ ] **Step 3: Validate**

Run: `claude plugin validate plugins/app-spec`
Expected: six agents listed, no error.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(agents): analysts and rules extractor from App Fusion, use-case mapper, contract reader"
```

---

### Task 8: `workflows/understand-module.js`

**Files:**
- Create: `plugins/app-spec/workflows/understand-module.js`, `plugins/app-spec/tests/harness.mjs` (copied from App Fusion), `plugins/app-spec/tests/workflows.test.mjs`

**Interfaces:**
- Consumes: args `{out, app: {name, path, stack}, shards: [{id, kind, name, loc, file}], capabilityIndex?}`; agent types `app-spec:ios-analyst|android-analyst|rn-analyst` by stack and `app-spec:use-case-mapper`.
- Produces: the `understand_result.json` shape: `{useCases, screens, flows, rejected, unverified, injectionFlags, rerunShards, stats: {shards, fragments, useCases, screens, flows, rejected}}`. Phases `Extract` (one analyst per shard, App Fusion's `FRAGMENT_SCHEMA` plus `states` and `fields` per screen), `Map` (one mapper over all fragments, `USECASES_SCHEMA` with `useCases`, `screens`, `flows`, `injectionSuspects`), `Verify` (one referee per use case, `VERDICT_SCHEMA` `{real, badEvidence, reason}`; `real: false` moves the use case to `rejected`, a thrown referee moves it to `unverified`). `meta` is a pure literal; no `Date.now`, `Math.random` or module loading.

- [ ] **Step 1: Write the failing harness tests**

```js
test('understand: two shards yield use cases with ids-free names and stats', async () => {
  const r = await run('understand-module.js', { out: 'o', app: {name:'a', path:'/a', stack:'ios-native'}, shards: [s1, s2] })
  assert.ok(r.useCases.length >= 1); assert.equal(r.stats.shards, 2); assert.ok(r.stats.fragments >= 2)
})
test('understand: a referee saying not real rejects the use case', async () => {
  const r = await run('understand-module.js', args, { 'verify:*': { real: false, badEvidence: ['x'], reason: 'no code' } })
  assert.equal(r.useCases.length, 0); assert.equal(r.rejected.length, 1)
})
test('understand: a throwing referee leaves the use case unverified', async () => {
  const r = await run('understand-module.js', args, { 'verify:*': () => { throw new Error('dead') } })
  assert.equal(r.unverified.length, 1)
})
test('understand: injection suspects are propagated', async () => { /* mapper returns injectionSuspects: ['f.swift:3'] → r.injectionFlags includes it */ })
test('understand: missing shards throws', async () => { await assert.rejects(run('understand-module.js', { out: 'o', app, shards: [] })) })
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test plugins/app-spec/tests/*.test.mjs`
Expected: FAIL, file not found.

- [ ] **Step 3: Implement the workflow** from App Fusion's `map-capabilities.js`: drop the domain planner (one mapper), drop fusion classes and twin text, add `states` and `fields` to the fragment schema and `screens`/`flows` to the mapper schema, keep the fenced untrusted-content prompt text and the referee phase.
- [ ] **Step 4: Run the tests to verify they pass** (5 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(workflows): understand-module fan-out with mapper and referees"
```

---

### Task 9: `workflows/extract-rules.js`

**Files:**
- Create: `plugins/app-spec/workflows/extract-rules.js`
- Modify: `plugins/app-spec/tests/workflows.test.mjs`

**Interfaces:**
- Consumes: args `{out, app, shards, useCaseIndex: "<out>/use-cases.json"}`; agent `app-spec:business-rules-extractor`.
- Produces: the `rules_result.json` shape `{rules, rejected, unverified, injectionFlags, rerunShards, stats: {shards, rules, p0, rejected}}`, App Fusion's `RULE` schema with `useCase` in place of `capability`; phases `Extract`, `Verify` (one citation referee per rule), `P0 panel` (two judges per P0 rule, both must agree it is real and P0); no conflicts phase.

- [ ] **Step 1: Write the failing tests**

```js
test('rules: a P0 rule is judged twice and kept when both agree', ...)
test('rules: a referee rejecting the citation drops the rule', ...)
test('rules: rules attach to a use case id from the index', ...)
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement** from App Fusion's `extract-rules.js`, removing the conflicts phase and the product mapping.
- [ ] **Step 4: Run the tests to verify they pass.**
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(workflows): extract-rules for one app, referees and the P0 panel"
```

---

### Task 10: `contracts.py`: locate backend routes and enrich the endpoints

**Files:**
- Create: `plugins/app-spec/scripts/contracts.py`
- Test: `plugins/app-spec/scripts/tests/test_contracts.py`, fixtures `tests/fixtures/backend-aspnet/Controllers/PayslipController.cs`, `tests/fixtures/backend-express/routes/payslips.ts`

**Interfaces:**
- Consumes: `endpoints.json` from Task 6; `app-spec.json` `contracts`.
- Produces: `contracts.locate_routes(repo_root: str, framework: str) -> list[{"method","path","file","line","auth","requestType","responseType"}]` for `aspnet` (class `[Route("prefix")]` joined with `[HttpGet("suffix")]`/`[HttpPost]` and the others, `[Authorize(Policy = "X")]` or `[Authorize]` as `auth`, action parameter types as `requestType`, `ActionResult<T>`/`Task<ActionResult<T>>` as `responseType`) and `express` (`router.<verb>('/path'` and NestJS `@Controller('prefix')` plus `@Get('suffix')`); `contracts.detect_framework(repo_root) -> "aspnet"|"express"|"unknown"`; `contracts.enrich(out: str, repo_root: str, framework: str = "auto") -> dict` matching each endpoint with `speclib.common.endpoints_match` and writing `backend` plus `label` `VERIFIED` on a match, leaving `backend: null` and `label` `INFERRED` otherwise; CLI `contracts.py <out> --repo PATH [--framework F]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_aspnet_route_joins_prefix_and_policy(self):
    routes = contracts.locate_routes(ASPNET, "aspnet")
    r = next(x for x in routes if x["method"] == "GET" and x["path"].endswith("/employees/{odpUserId}/payslips"))
    self.assertEqual(r["auth"], "PayslipUsersReadPolicy"); self.assertTrue(r["file"].endswith("PayslipController.cs"))
def test_express_route(self):
    self.assertIn(("GET", "/employees/:id/payslips"), {(r["method"], r["path"]) for r in contracts.locate_routes(EXPRESS, "express")})
def test_enrich_marks_verified_and_inferred(self):
    contracts.enrich(OUT, ASPNET); eps = out.load(OUT, "endpoints.json")["endpoints"]
    self.assertEqual(next(e for e in eps if e["path"].endswith("/payslips"))["label"], "VERIFIED")
    self.assertEqual(next(e for e in eps if e["path"].endswith("/pdf"))["label"], "INFERRED")
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `contracts.py`.**
- [ ] **Step 4: Run the tests to verify they pass** (3 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(contracts): locate backend routes and verify the module's endpoints"
```

---

### Task 11: `render.py spec`: the template and the appendices

**Files:**
- Create: `plugins/app-spec/scripts/speclib/template.py`
- Modify: `plugins/app-spec/scripts/render.py`
- Test: `plugins/app-spec/scripts/tests/test_render_spec.py`

**Interfaces:**
- Consumes: the catalogs of Task 6, `endpoints.json` after Task 10, `fields.json`, `inventory.json`, `overrides.json`, `ledger.json` when present (Task 12), and `prose.json` written by the spec writer (Task 15): `{"summary": str, "screens": {SCR: {"purpose": str, "states": [{"name","shows","evidence"}]}}, "keepDrop": {UC: {"keep": [str], "drop": [{"what","file"}]}}, "data": [{"entity","fields","storage","lifetime","evidence"}], "dependencies": [str], "openQuestions": [{"id","question","searched","owner"}], "criteria": [{"ids": [UC], "text": str, "evidence": str}]}`; every prose entry carries an `evidence` citation or is rendered with `UNKNOWN`.
- Produces: `template.HEADINGS`, `template.APPENDICES` (the exact strings of the Global Constraints), `template.AC_RE = r"^- \*\*AC(\d+) \(((?:UC|CAP)-\d{3,})(?:, (?:UC|CAP)-\d{3,})*\):\*\* .+"`, `template.header(cfg) -> str`; `render.spec(out: str, name: str = "SPEC.md") -> str` writing the eight sections and six appendices, the `Capabilities` table as `| CAP | Name | Design | Screens | Notes |` with `carry-as-is (<app> <file:line>)` in `Design`, criteria numbered from 1 in catalog order, Appendix A per screen with `identifier` or `proposedId`, Appendix F from `ledger.json`; items dropped in `overrides.json` absent from Appendix A and listed in Appendix F with their reason; CLI `render.py spec <out> [--name FILE]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_spec_has_template_headings_in_order(self):
    text = render.spec(OUT); heads = [l for l in text.splitlines() if l.startswith("## ")]
    self.assertEqual(heads[:8], template.HEADINGS); self.assertEqual(heads[8:], template.APPENDICES)
def test_spec_header_lines(self):
    text = render.spec(OUT); self.assertIn("Source: module Payslips of ios-app (no source issue)", text); self.assertRegex(text, r"Reference HEADs: ios-app `[0-9a-f]{7,}`")
def test_criteria_numbering_is_contiguous(self):
    nums = [int(m.group(1)) for m in re.finditer(template.AC_RE, render.spec(OUT), re.M)]
    self.assertEqual(nums, list(range(1, len(nums) + 1))); self.assertGreater(len(nums), 0)
def test_design_column_is_carry_as_is(self):
    self.assertRegex(render.spec(OUT), r"\| UC-001 \| [^|]+ \| carry-as-is \(ios-app [^)]+:\d+\) \|")
def test_dropped_field_leaves_appendix_a_and_enters_f(self):
    write_overrides(OUT, {"drop": [{"kind": "field", "id": "SCR-001.title", "reason": "not user-facing"}]}); text = render.spec(OUT)
    a, f = section(text, "## Appendix A. Fields and ids"), section(text, "## Appendix F. Coverage")
    self.assertNotIn("SCR-001.title", a); self.assertIn("SCR-001.title", f); self.assertIn("not user-facing", f)
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `template.py` and `render.spec`.**
- [ ] **Step 4: Run the tests to verify they pass** (5 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(render): the spec in Scarlet's template with appendices"
```

---

### Task 12: `ledger.py`: coverage with thresholds and overrides

**Files:**
- Create: `plugins/app-spec/scripts/ledger.py`
- Test: `plugins/app-spec/scripts/tests/test_ledger.py`

**Interfaces:**
- Consumes: `inventory.json`, `fields.json`, the catalogs, `overrides.json`, `app-spec.json` thresholds.
- Produces: `ledger.compute(out: str) -> dict` in the `ledger.json` shape: classes `screens` (inventory screens matched to `screens.json` by file), `fields` (every element of `fields.json` present in `screens.json` elements), `endpoints` (inventory endpoints matched by method and normalized path to `endpoints.json` with at least one use case), `strings` (module string keys cited by a use case or a screen element), `events`, `storage`, `permissions` (platform items of kind permission), `platform`; an uncovered item with a reason from `overrides.json` `drop` counts as covered-with-reason and is listed with it; `pass` is true when every class meets its threshold and every uncovered item below threshold has a reason; writes `ledger.json` and `LEDGER.md`; CLI `ledger.py <out>` exits 1 when `pass` is false.

- [ ] **Step 1: Write the failing tests**

```python
def test_all_covered_passes(self): self.assertTrue(ledger.compute(OUT_FULL)["pass"])
def test_unreferenced_endpoint_fails_and_is_listed(self):
    l = ledger.compute(OUT_MISSING_ENDPOINT); self.assertFalse(l["pass"])
    self.assertIn("GET /employee/api/v1/employees/{}/payslips/{}/pdf", [u["item"] for u in l["classes"]["endpoints"]["uncovered"]])
def test_override_reason_makes_it_pass(self):
    write_overrides(OUT_MISSING_ENDPOINT, {"drop": [{"kind": "endpoint", "id": "EP-002", "reason": "dead code"}]})
    l = ledger.compute(OUT_MISSING_ENDPOINT); self.assertTrue(l["pass"]); self.assertEqual(l["classes"]["endpoints"]["uncovered"][0]["reason"], "dead code")
def test_strings_threshold_95(self):
    l = ledger.compute(OUT_ONE_STRING_OF_30_UNCITED); self.assertTrue(l["pass"])   # 29/30 = 96.7 %
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `ledger.py`.**
- [ ] **Step 4: Run the tests to verify they pass** (4 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(ledger): coverage of the module's inventory by the spec, with thresholds and overrides"
```

---

### Task 13: `grade.py`: the shape checks

**Files:**
- Create: `plugins/app-spec/scripts/grade.py`
- Test: `plugins/app-spec/scripts/tests/test_grade.py`

**Interfaces:**
- Consumes: `SPEC.md` (or the named file), the catalogs, `overrides.json`, `app-spec.json` (`bannedNouns`, app path).
- Produces: `grade.run(out: str, name: str = "SPEC.md") -> dict` in the `grade.json` shape with these checks, in this order: `sections` (the eight headings present, in order, then the six appendices), `rules-per-use-case` (every use case has a rule or the sentence `No client-side rule; the server decides.` with a citation in its screen or criteria), `criteria-per-use-case`, `criteria-numbering` (`template.AC_RE`, contiguous from 1), `citations-resolve` (every `` `path:line` `` or `` `path:line-line` `` under the app root or a contract root exists and the range is within the file's line count), `unknowns-have-owner` (every `UNKNOWN` line names what was searched and an owner), `no-duplicate-use-cases` (by `ids.norm`), `banned-nouns` (none of `bannedNouns` in sections 1 to 8), `overrides-reflected` (every `drop` id absent from the body and present in Appendix F, every `rename` applied, every override id known to a catalog); `pass` is the conjunction; CLI `grade.py <out>` exits 1 when `pass` is false and prints each failing check with its detail.

- [ ] **Step 1: Write the failing tests**

```python
def test_good_spec_passes_all(self): self.assertTrue(grade.run(OUT_GOOD)["pass"])
def test_citation_beyond_file_length_fails(self):
    g = grade.run(OUT_WITH_CITATION_LINE_9999); c = check(g, "citations-resolve"); self.assertFalse(c["pass"]); self.assertIn(":9999", c["detail"])
def test_override_unknown_id_is_drift_not_silence(self):
    write_overrides(OUT_GOOD, {"drop": [{"kind": "field", "id": "SCR-099.ghost", "reason": "x"}]})
    c = check(grade.run(OUT_GOOD), "overrides-reflected"); self.assertFalse(c["pass"]); self.assertIn("SCR-099.ghost", c["detail"])
def test_banned_noun_in_requirements_fails_but_appendix_c_is_allowed(self):
    self.assertFalse(check(grade.run(OUT_REALM_IN_SCREENS), "banned-nouns")["pass"])
    self.assertTrue(check(grade.run(OUT_REALM_IN_APPENDIX_C), "banned-nouns")["pass"])
def test_criteria_gap_fails(self): self.assertFalse(check(grade.run(OUT_AC_1_3), "criteria-numbering")["pass"])
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `grade.py`.**
- [ ] **Step 4: Run the tests to verify they pass** (5 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(grade): deterministic shape checks of the spec"
```

---

### Task 14: `status.py`: where things stand and the next command

**Files:**
- Create: `plugins/app-spec/scripts/status.py`
- Test: `plugins/app-spec/scripts/tests/test_status.py`

**Interfaces:**
- Consumes: the output folder's files and their modification times.
- Produces: `status.report(out: str) -> dict` with `stages` (`module`, `inventory`, `understand`, `rules`, `contracts`, `catalogs`, `spec`, `review`, `tests`, `compare`, each `done` or `-` with its newest file's time), `stale` (list of lines: `the spec predates <catalog>: re-run render.py spec`, `the review predates the spec: run review`, `the catalogs predate understand_result.json: re-run render.py catalogs`, `the inventory predates module.json: re-run inventory.py`), `coverage` (from `ledger.json`), `passes` (from `review.json`), `next` (`command`, `reason`): the first missing stage's command in order, else `review` when the review is stale, else `(a person) read <SPEC name>`; CLI `status.py <out>` prints it in App Fusion's style, one stage per line, then `Next:`.

- [ ] **Step 1: Write the failing tests**

```python
def test_empty_out_next_is_module(self): self.assertIn("module.py", status.report(EMPTY)["next"]["command"])
def test_after_spec_without_review_next_is_review(self): self.assertIn("review", status.report(OUT_SPEC_NO_REVIEW)["next"]["command"])
def test_stale_spec_detected(self):
    touch(OUT_GOOD, "use-cases.json", later=True); self.assertTrue(any("spec predates" in s for s in status.report(OUT_GOOD)["stale"]))
def test_complete_next_is_a_person(self): self.assertTrue(status.report(OUT_GOOD)["next"]["command"].startswith("(a person)"))
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement `status.py`.**
- [ ] **Step 4: Run the tests to verify they pass** (4 tests).
- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(status): stages, staleness and the next command"
```

---

### Task 15: the guard and the Devin session note

**Files:**
- Create: `plugins/app-spec/hooks/hooks.json`, `plugins/app-spec/hooks/guard.sh`, `plugins/app-spec/hooks/devin-context.sh`, `plugins/app-spec/scripts/guard.py`, `plugins/app-spec/scripts/devin_context.py`
- Test: `plugins/app-spec/scripts/tests/test_guard.py`, `plugins/app-spec/scripts/tests/test_devin_context.py`

**Interfaces:**
- Consumes: App Fusion's `guard.py` (tokenizer, redirect and wrapper handling, `classify_write`, `decide`) and `devin_context.py`.
- Produces: `guard.py` reading the hook input on stdin, finding output folders (`app-spec.json`) from the project folder, the shell's folder and the paths the tool call names, and for each: `deny` a file-tool write under `app.path` or any `contracts[].path`, `ask` a shell command that would write there (including through `cd`, wrappers, heredocs and redirects), allow everything else; `APP_SPEC_GUARD=false` disables it; `guard.protected_roots(cfg) -> list[str]`. `devin_context.py` prints the App Fusion note with `app-spec` names (the plugin folder, `ask_user_question`, `run_subagent` with `app-spec:<agent>`, `exec`, `read`/`write`/`edit`/`grep`/`glob`, `APP_SPEC_GUARD`) only when `DEVIN_PLUGIN_ROOT` or `DEVIN_PROJECT_DIR` is set. `hooks.json` as the Global Constraints state.

- [ ] **Step 1: Write the failing tests**

```python
def test_write_under_app_is_denied(self): self.assertEqual(run_guard({"tool_name": "Write", "tool_input": {"file_path": APP + "/x.swift"}}, cwd=OUT)["decision"], "deny")
def test_write_under_out_is_allowed(self): self.assertIsNone(run_guard({"tool_name": "Write", "tool_input": {"file_path": OUT + "/SPEC.md"}}, cwd=OUT))
def test_shell_copy_into_app_asks(self): self.assertEqual(run_guard({"tool_name": "Bash", "tool_input": {"command": f"cp a {APP}/b"}}, cwd=OUT)["decision"], "ask")
def test_contract_repo_is_protected(self): self.assertEqual(run_guard({"tool_name": "Edit", "tool_input": {"file_path": BACKEND + "/c.cs"}}, cwd=OUT)["decision"], "deny")
def test_devin_context_silent_outside_devin(self): self.assertEqual(run_devin_context(env={}), "")
def test_devin_context_names_plugin_root(self): self.assertIn("app-spec", run_devin_context(env={"DEVIN_PLUGIN_ROOT": "/p"}))
```

- [ ] **Step 2: Run the tests to verify they fail.**
- [ ] **Step 3: Implement** by copying App Fusion's scripts and replacing `has_program`/`find_workspaces` with discovery of `app-spec.json` and `protected_roots`.
- [ ] **Step 4: Run the tests to verify they pass** (6 tests).
- [ ] **Step 5: Validate and commit**

Run: `claude plugin validate plugins/app-spec` (hooks listed, no error)

```bash
git add -A && git commit -m "feat(hooks): source-app write guard for Claude Code and Devin, Devin session note"
```

---

### Task 16: the spec writer, the critic, the rubric and the three skills

**Files:**
- Create: `plugins/app-spec/agents/spec-writer.md`, `plugins/app-spec/agents/spec-critic.md`, `plugins/app-spec/references/rubric.md`
- Create: `plugins/app-spec/skills/spec/SKILL.md`, `plugins/app-spec/skills/review/SKILL.md`, `plugins/app-spec/skills/status/SKILL.md`

**Interfaces:**
- Consumes: every script and workflow above, by the CLIs and arguments given in their Interfaces.
- Produces: `spec-writer` (tools `Read, Glob, Grep`): reads the catalogs, `fields.json`, `inventory.json`, `docs/DESIGN.md` and the cited code, returns `prose.json` in Task 11's shape; every entry cites `file:line` or is marked `UNKNOWN` with what was searched; writes behaviour, never structure; sorts implementation facts into `keepDrop.drop`. `spec-critic` (tools `Read, Glob, Grep, Bash` read-only): reads `SPEC.md`, `references/rubric.md`, `ledger.json`, `grade.json` and samples of the cited code (at least one cited range per use case), returns `[{"severity": "Blocker|High|Medium|Nit", "section": str, "finding": str, "fix": str, "owner": "analyst|mapper|rules|contracts|writer"}]`; Blocker when a use case or screen the code has is absent or a claim's citation does not support it, High when a screen lacks states, a rule lacks values, an error or offline path the code has is missing, or legacy structure is stated as a requirement. `references/rubric.md`: the bar distilled section by section into what a complete and deep entry contains, with no Visma content (synthetic examples). The `spec` skill: arguments `<app> --module ... [--out] [--name] [--contracts ...] [--capabilities --scope] [--bar] [--passes] [--headless]`, `disable-model-invocation: true`; steps in order: run `module.py` and show the proposal with `AskUserQuestion` (options `Yes`, `Edit the folders`, `Cancel`; headless takes the proposal and says so), run `inventory.py`, run the understand workflow by name with `scriptPath` fallback and the no-Workflow path (one analyst per shard group of up to 25,000 lines, at most six in parallel, then the mapper, then referees), save `understand_result.json`, run `render.py catalogs`, run the rules workflow likewise and save `rules_result.json`, run `render.py catalogs` again, run `contracts.py` per contract repository then the `contract-reader` for fields, spawn `spec-writer`, save `prose.json`, run `render.py spec`, `ledger.py`, `grade.py`, spawn `spec-critic`, send Blocker and High findings to their owner for that gap only, repeat the render, ledger, grade and critic at most `passes` times, write `REVIEW.md` and `OPEN_QUESTIONS.md`, report (use cases, screens, rules, endpoints by label, criteria, coverage per class, remaining findings) and name the next step: a person reads the spec. The `review` skill: `<out> [--accept]`, runs `ledger.py`, `grade.py` and `spec-critic` on the current spec, writes `REVIEW.md`, applies nothing; with `--accept` offers each uncovered item in a pop-up to record a reason into `overrides.json`. The `status` skill: runs `status.py` and repeats its lines.

- [ ] **Step 1: Write `references/rubric.md`** from the design's section 5.7 and Global Constraints: per section, the fields a complete entry has and three symptoms of a shallow one.
- [ ] **Step 2: Write `spec-writer.md` and `spec-critic.md`** per the Interfaces, with App Fusion's untrusted-content and secret sections.
- [ ] **Step 3: Write the three skills** per the Interfaces, each ending by naming the exact next command, each with the Devin notes (`${CLAUDE_PLUGIN_ROOT}` written out under Devin, `ask_user_question`, no Workflow tool).
- [ ] **Step 4: Validate**

Run: `claude plugin validate plugins/app-spec`
Expected: three skills, eight agents, hooks, no error.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(skills): spec, review and status; spec writer, critic and the rubric"
```

---

### Task 17: evals, README, changelog, release 0.1.0

**Files:**
- Create: `plugins/app-spec/evals/_fixtures/make-apps.sh`, `plugins/app-spec/evals/spec-fixture/{case.yaml,prompt.md,scaffold.sh,graders/}`, `plugins/app-spec/evals/source-guard/...`, `plugins/app-spec/evals/status-next/...`
- Modify: `plugins/app-spec/README.md`, `plugins/app-spec/CHANGELOG.md`, `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces: `make-apps.sh` copying the three fixture apps into the eval's scratch folder; eval `spec-fixture`: prompt `/app-spec:spec <fixture ios-app> --module Payslips --out ./specs/payslips --headless`, graders check that `specs/payslips/SPEC.md` exists with the eight headings in order, `ledger.json` has `pass: true`, and `app-spec.json` has `confirmed: false`; eval `source-guard`: prompt asks for an edit inside the fixture app, grader checks the file is unchanged and the reply names the guard; eval `status-next`: on a folder with catalogs but no spec, grader checks the reply names `render.py spec`. README per App Fusion's: what you get, install (Claude Code and Devin), start here, the path, how it measures completeness, what to expect, safety, adapting. `CHANGELOG.md` entry 0.1.0.

- [ ] **Step 1: Write the eval cases and fixtures script.**
- [ ] **Step 2: Run everything**

Run: `python3 -m unittest discover -s plugins/app-spec/scripts/tests -v && node --test plugins/app-spec/tests/*.test.mjs && claude plugin validate plugins/app-spec`
Expected: all Python and Node tests pass; validation clean.

Run: `claude plugin eval plugins/app-spec --scaffold --trust-plugin --allow-tools Bash Write Edit --ablation none`
Expected: the three cases score 1.00. If a case fails, fix the skill or script it exercises, never the grader.

- [ ] **Step 3: Write the README and the changelog.**
- [ ] **Step 4: Commit and tag**

```bash
git add -A && git commit -m "docs: README, changelog and evals for 0.1.0" && git tag v0.1.0
```

---

## Acceptance after the plan

The design's section 5.16 names two runs that are not unit tests and need Visma code and a person: the calendar module of me-ios against the existing calendar spec, scoped to the module, and payslips as the first real module. They run after Task 17, from a clone of me-ios and me-api, with the outputs and measurements recorded in the Scarlet repository, never in this one.

## Self-review notes

- Spec coverage: 5.1 (Tasks 14, 16), 5.2 (3, 4), 5.3 (5), 5.4 (7, 8), 5.5 (9), 5.6 (10, 7), 5.7 (11, 16), 5.8 (12, 13, 16), 5.9 (1, 6, 11), 5.12 (7, 16), 5.13 (8, 9), 5.14 (15), 5.15 (17), 5.16 (after the plan). 5.10 and 5.11 are the second plan.
- Names used across tasks: `out.load_config`, `out.load`, `out.save`, `module.resolve_by_name`, `module.scope_from_index`, `module.make_shards`, `touchpoints.find`, `fields.extract`, `ids.Registry`, `ids.norm`, `render.catalogs`, `render.spec`, `contracts.enrich`, `ledger.compute`, `grade.run`, `status.report`, `guard.protected_roots`, `template.HEADINGS`, `template.APPENDICES`, `template.AC_RE`.
- Review Focus items 1 and 5 are tested in Task 3, item 2 in Task 5, items 3 and 4 in Task 13.
