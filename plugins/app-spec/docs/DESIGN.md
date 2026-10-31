# App Spec: design contract

This file is the contract between the skills, agents, workflows and scripts of App Spec. When they disagree, this file
wins. Later parts cite its section names and never redefine a shape. The reasons behind the decisions are in
`docs/superpowers/specs/2026-10-30-app-spec-design.md` at the repository root.

## Purpose

A developer points a command at one module of one existing mobile app and gets back a spec that is complete and deep
enough to plan and build the same feature in a new app without reading the old code again. The spec follows a fixed
template, so the team's issue and planning tools read it without change. Completeness is measured by a deterministic
inventory and a coverage ledger, and a critic reviews the draft before a person reads it.

## Words

| Word | Meaning |
| --- | --- |
| Module | One feature of the app that a person names: a name, or a set of folders. The unit of one run |
| Core | The files of the module itself: its folders, found from the name or given by the person |
| Touch point | A file outside the core that the module needs or that needs the module, with the reason it was pulled in (shared types, string keys, analytics events, navigation entries, start-page components, assistant tools) |
| Use case | One thing a person can do in the module, named with a verb in business words. `UC-NNN`. With a capability index it can carry a `CAP-NNN` alias |
| Screen | One screen or screen state the user sees, with its actions, states and fields. `SCR-NNN` |
| Flow | A path through the module in 3 to 8 numbered steps, each naming a screen and its use cases. `FLOW-NNN`. Flows become the end-to-end tests |
| Rule | One business rule card with plain English, Given/When/Then with concrete values, and a priority. `RULE-NNN` |
| Endpoint | One HTTP call the module makes, as `METHOD /path`, with request and response fields and errors. `EP-NNN` |
| Override | A person's correction recorded in `overrides.json`: a drop, a rename, an id mapping or a merge, each with a reason. A re-run never overwrites it |

Other words used below:

| Word | Meaning |
| --- | --- |
| Output folder | The folder `<out>` that holds every file a run writes. The only place the plugin writes |
| Shard | A slice of the module's files that one analyst reads. At most 9,000 non-blank lines by default |
| Contract repository | A backend repository read-only as a source for endpoint contracts |
| Capability index | An optional `capability_index.json` from an App Fusion program, used only to alias `CAP-NNN` ids |

## Output folder

Every script reads and writes this layout. Paths inside JSON files are relative to the app root unless a field says
otherwise. Every JSON file has `"version": 1` unless its shape shows no version. Models never write a catalog file
directly: workflows return `understand_result.json` and `rules_result.json`, and `render.py` turns them into the
catalogs and ids.

```
<out>/
  app-spec.json         run configuration and source identity       (written by module.py, which updates its own fields in place; never rewritten from scratch)
  overrides.json        a person's corrections                       (written by a person or `review --accept`; never regenerated)
  module.json           core, touch points, string keys, shards
  shards/<id>.json      what each analyst reads
  inventory.json, INVENTORY.md      deterministic inventory scoped to the module
  fields.json           field inventory per screen
  understand_result.json, rules_result.json   the workflows' results, as returned (patches/ folded in by patch_result.py)
  contracts/batch-<k>.json, contracts_result.json   the contract reader's envelopes, and their merge (merge_contracts.py)
  patches/<name>.json   partial results of a follow-up run or a review fix, before they are folded in
  ids.json              the id registry                              (updated in place by render.py; never regenerated)
  use-cases.json, screens.json, flows.json, rules.json, endpoints.json   the catalogs, rendered
  prose.json            the spec writer's prose, as returned
  ledger.json, LEDGER.md            coverage per class
  grade.json            shape checks
  critic-<n>.json       the critic's findings of one pass, as returned
  review.json, REVIEW.md            the scorecard of every review pass          (reset by `spec`; `review` appends a pass)
  SPEC.md (or --name)   the deliverable
  OPEN_QUESTIONS.md
```

A re-run of `spec` regenerates every file except three. `overrides.json` is never touched. `app-spec.json` is updated in place by `module.py`, which sets `module.query`, `contracts`, `capabilityIndex`, `scope` and `app.commit`, `app.branch`, `app.clean` from the current arguments and repository state, sets `module.confirmed` to true when `--confirmed` is passed and `options.locale` when `--locale` is passed, and keeps every other field. `ids.json` is updated in place by `render.py`: existing keys keep their ids, retired keys stay, new keys take `max + 1`, so no id is ever reused. A `spec` re-run resets `review.json` and `REVIEW.md`, and the `review` command appends one pass to them.

### app-spec.json

```json
{"version":1,
 "app":{"path":"/abs/path","name":"me-ios","stack":"ios-native","commit":"<sha>","branch":"main","clean":true},
 "module":{"query":["payslips"],"confirmed":false},
 "contracts":[{"path":"/abs/path","name":"me-api","commit":"<sha>"}],
 "capabilityIndex":null,
 "scope":null,
 "options":{"passes":2,"locale":"en","specName":"SPEC.md",
            "thresholds":{"screens":100,"endpoints":100,"events":100,"permissions":100,"storage":100,"strings":95,"fields":95},
            "bannedNouns":["Realm","Swinject","NotificationCenter","ViewModel","Redux","Hilt","Room"]},
 "created":"2026-10-30T09:00:00Z"}
```

| Field | Meaning |
| --- | --- |
| `app.path` | Absolute path of the analysed app. The guard denies writes under it |
| `app.name` | Short name of the app, used in header lines |
| `app.stack` | `ios-native`, `android-native` or `react-native`, from stack detection |
| `app.commit` | The app's HEAD sha when the run started |
| `app.branch` | The branch checked out at that time |
| `app.clean` | `true` when the working tree had no uncommitted changes |
| `module.query` | The module name or the folders and globs the person gave |
| `module.confirmed` | `true` when a person confirmed the proposed scope, `false` for a headless run |
| `contracts` | Backend repositories read as contract sources, each with its path, name and HEAD sha. Empty list when none |
| `capabilityIndex` | Path to a `capability_index.json`, or `null` |
| `scope` | List of `CAP-NNN` ids that define the module through the capability index, or `null` |
| `options.passes` | Most review rounds. Default 2, range 1 to 5 |
| `options.specName` | File name of the spec inside `<out>`, as the spec skill wrote it with `--name`. Optional, default `SPEC.md`. `status.py` reads it |
| `options.locale` | Source-language code of the strings the spec quotes. Default `en` |
| `options.thresholds` | Coverage percent per class. See Thresholds and defaults |
| `options.bannedNouns` | Legacy nouns the grader forbids in requirement sentences outside Appendix C |
| `created` | ISO 8601 time of the first run |

### overrides.json

```json
{"version":1,
 "drop":[{"kind":"field|screen|useCase|endpoint|string|event|storage|permission|platform","id":"...","reason":"..."}],
 "rename":[{"id":"...","name":"..."}],
 "ids":{"SCR-001.title":"pay.list.title"},
 "merge":[{"into":"UC-003","from":["UC-007"]}]}
```

| Field | Meaning |
| --- | --- |
| `drop` | Items the spec leaves out. A dropped field is absent from Appendix A and listed in Appendix F with its reason |
| `drop[].kind` | The class of the dropped item |
| `drop[].id` | The id of the item: a catalog id, a string key, an event name, a storage key, a permission key, or for `platform` the item as `<section>:<value>` (a whole section by its name) |
| `drop[].reason` | Why the item is dropped. Required |
| `rename` | New display names, by id. The id stays |
| `ids` | Proposed accessibility ids for the new app, keyed by `<SCR id>.<element name>` |
| `merge` | Use cases folded into another. The `from` ids are retired and never reused |

### module.json

```json
{"version":1,"core":["Modules/Payslips/PayslipList.swift"],
 "touchPoints":[{"file":"Shared/Net/Client.swift","reason":"request class the core defines and others use"}],
 "stringKeys":["pay.list.title"],
 "shards":[{"id":"core-01","kind":"core|touch","name":"Payslips","files":["rel"],"loc":9000,"file":"shards/core-01.json"}],
 "loc":18000}
```

| Field | Meaning |
| --- | --- |
| `core` | Files of the module itself |
| `touchPoints[].file` | A file outside the core that the module needs or that needs the module |
| `touchPoints[].reason` | Why it was pulled in |
| `stringKeys` | String keys the core's screens use |
| `shards[].id` | Shard id, also the file name under `shards/` |
| `shards[].kind` | `core` for module files, `touch` for touch points |
| `shards[].name` | Human name of the shard |
| `shards[].files` | Files in the shard |
| `shards[].loc` | Non-blank lines in the shard. At most 9,000 by default |
| `shards[].file` | Path of the shard file inside `<out>` |
| `loc` | Total non-blank lines of core and touch points |

### shards/&lt;id&gt;.json

What one analyst reads. `module.py` writes one file per shard, and workflows pass only the file path to the agent.

```json
{"id":"core-01","kind":"core|touch","name":"Payslips","files":["rel"],"loc":9000,
 "hints":{"routes":[],"screens":[],"endpoints":[],"events":[]}}
```

| Field | Meaning |
| --- | --- |
| `id`, `kind`, `name`, `files`, `loc` | As the same fields of the shard entry in `module.json` |
| `hints` | The inventory entries whose file is inside the shard, as lists of routes, screens, endpoints and events. Empty lists when the inventory has not run yet. `inventory.py` fills them: screens and routes by name, endpoints as `METHOD /path`, events by name |

### inventory.json and INVENTORY.md

App Fusion's inventory shape, scoped to the files in `module.json`. Every count carries the one-line rule that
produced it. Two counts produced by different rules are different facts. `INVENTORY.md` is the rendered view.

### fields.json

```json
{"version":1,
 "screens":[{"screen":"PayslipList","file":"Modules/Payslips/PayslipList.swift:12",
   "elements":[{"kind":"text|input|button|toggle|picker|list|image|document|other",
                "textKey":"pay.list.title","text":"Payslips","identifier":"payslipListTitle",
                "file":"Modules/Payslips/PayslipList.swift","line":30}]}]}
```

| Field | Meaning |
| --- | --- |
| `screens[].screen` | The screen name as the code names it |
| `screens[].file` | `rel:line` where the screen is declared |
| `elements[].kind` | What the element is: text, input, button, toggle, picker, list, image, document or other |
| `elements[].textKey` | The string key the element shows, or `null` |
| `elements[].text` | The source-language text, or `null` |
| `elements[].identifier` | The accessibility id or test tag the old app already has, or `null` |
| `elements[].file`, `elements[].line` | Where the element is declared |

### understand_result.json

The result of `understand-module.js`, as returned. Workflows refer to use cases and screens by **name**. The renderer
assigns ids.

```json
{"useCases":[{"name":"View payslip list","description":"...","personas":["employee"],"permissions":["..."],
              "screens":["PayslipList"],"files":["rel"],"endpoints":["GET /payslips"],"events":["payslip_opened"],
              "strings":["pay.list.title"],"storage":["lastPayslipId"],"platform":["push:payslip"],
              "rulesHint":"...","evidence":"VERIFIED"}],
 "screens":[{"name":"PayslipList","file":"rel:line","useCases":["View payslip list"],"actions":["open a payslip"],
             "states":[{"name":"empty","shows":"No payslips yet","evidence":"VERIFIED"}],
             "fields":[{"kind":"text","textKey":"pay.list.title","text":"Payslips","identifier":null,"file":"rel","line":30}]}],
 "flows":[{"name":"Read the latest payslip","persona":"employee",
           "steps":[{"screen":"PayslipList","useCases":["View payslip list"],"action":"tap the first row"}]}],
 "rejected":[],"unverified":[],"injectionFlags":[],"rerunShards":[],"stats":{}}
```

| Field | Meaning |
| --- | --- |
| `useCases[].name` | Verb-first name in business words. The normalized name is the id key |
| `useCases[].description` | What the person achieves |
| `useCases[].personas` | Who does it |
| `useCases[].permissions` | Roles, flags and system permissions that gate it |
| `useCases[].screens` | Screen names it uses |
| `useCases[].files` | Files that implement it, as `rel` or `rel:line` |
| `useCases[].endpoints` | Calls it makes, as `METHOD /path` |
| `useCases[].events` | Analytics event names it sends |
| `useCases[].strings` | String keys it shows |
| `useCases[].storage` | Local storage keys it reads or writes |
| `useCases[].platform` | Platform features it uses (push, links, extensions, background work, sharing) |
| `useCases[].rulesHint` | Pointer for the rules extractor: where the rules of this use case are |
| `useCases[].evidence` | `VERIFIED`, `INFERRED` or `UNKNOWN` |
| `screens[].name`, `file` | Screen name and `rel:line` of its declaration |
| `screens[].useCases` | Use-case names that happen on this screen |
| `screens[].actions` | What the user can do on it |
| `screens[].states[]` | Each state (loading, empty, error, success, offline, no permission, confirmation): `name`, `shows` what the user sees, and `evidence` |
| `screens[].fields[]` | Confirmed elements in the shape of `fields.json` elements |
| `flows[].name`, `persona` | Flow name and who walks it |
| `flows[].steps[]` | Ordered steps: the `screen` name, the `useCases` names, and the `action` |
| `rejected` | Fragments a referee rejected, each with the reason |
| `unverified` | Claims whose citations the referee could not check |
| `injectionFlags` | Instruction-shaped text found in analysed content, with `file:line`. Never acted on |
| `rerunShards` | Ids of shards that failed and need a re-run |
| `stats` | Counts and timings of the run |

### rules_result.json

The result of `extract-rules.js`, as returned.

```json
{"rules":[{"name":"Payslip hides gross for part-timers","category":"display","priority":"P1","source":"rel:line",
           "plainEnglish":"...","given":"...","when":"...","then":"...","parameters":[{"name":"x","value":"3"}],
           "edgeCases":["..."],"suspectedDefect":null,"confidence":"High","question":null,"useCase":"View payslip list"}],
 "rejected":[],"unverified":[],"injectionFlags":[],"rerunShards":[],"stats":{}}
```

| Field | Meaning |
| --- | --- |
| `rules[].name` | Short name. The normalized name is the id key |
| `rules[].category` | Kind of rule: validation, calculation, default, ordering, offline, flag, permission, display |
| `rules[].priority` | `P0`, `P1` or `P2` |
| `rules[].source` | `rel:line` range of the code that enforces it |
| `rules[].plainEnglish` | The rule in one or two sentences |
| `rules[].given`, `when`, `then` | Given/When/Then with concrete values |
| `rules[].parameters` | Constants and thresholds with their current values |
| `rules[].edgeCases` | Boundary and failure cases the code handles |
| `rules[].suspectedDefect` | A likely bug in the old code that the new app should not copy, or `null` |
| `rules[].confidence` | `High`, `Medium` or `Low` |
| `rules[].question` | The question for the owner when confidence is below High, or `null` |
| `rules[].useCase` | The name of the use case it belongs to, or an empty string |
| `rejected`, `unverified`, `injectionFlags`, `rerunShards`, `stats` | As in `understand_result.json` |

### use-cases.json

```json
{"version":1,"useCases":[{"id":"UC-001","alias":"CAP-225","name":"...","description":"...","personas":[],"permissions":[],
  "screens":["SCR-001"],"files":[],"endpoints":["EP-001"],"events":[],"strings":[],"storage":[],"platform":[],"evidence":"VERIFIED"}]}
```

| Field | Meaning |
| --- | --- |
| `id` | The `UC-NNN` id |
| `alias` | The `CAP-NNN` id from the capability index when the outcome matches, else `null` |
| `screens` | `SCR-NNN` ids |
| `endpoints` | `EP-NNN` ids |
| `rulesHint` | Not carried into `use-cases.json` |
| `screens` | `SCR-NNN` ids here. `understand_result.json` holds screen names |
| Other fields | As in `understand_result.json` |

### screens.json

```json
{"screens":[{"id":"SCR-001","name":"PayslipList","file":"rel:line","useCases":["UC-001"],"actions":["open a payslip"],
  "states":[{"name":"empty","shows":"No payslips yet","evidence":"VERIFIED"}],
  "elements":[{"kind":"text","textKey":"pay.list.title","text":"Payslips","identifier":null,"file":"rel","line":30,
               "proposedId":"payslipListTitle"}]}]}
```

| Field | Meaning |
| --- | --- |
| `id` | The `SCR-NNN` id |
| `useCases` | `UC-NNN` ids |
| `elements` | The `fields.json` elements for this screen, merged with the analysts' confirmed fields |
| `elements[].proposedId` | The accessibility id the new app should use. The old id when it has one, else a proposal, else from `overrides.json` |
| Other fields | As in `understand_result.json` |

### flows.json

```json
{"flows":[{"id":"FLOW-001","name":"...","persona":"employee","steps":[{"screen":"SCR-001","useCases":["UC-001"],"action":"..."}]}]}
```

Fields are as in `understand_result.json` with names replaced by ids.

### rules.json

```json
{"rules":[{"id":"RULE-001","useCase":"UC-001","name":"...","category":"display","priority":"P1","confidence":"High",
  "plainEnglish":"...","given":"...","when":"...","then":"...","parameters":[],"edgeCases":[],
  "suspectedDefect":null,"question":null,"source":"rel:line"}]}
```

`useCase` is a `UC-NNN` id or `null` when the rule belongs to no use case. Other fields are as in `rules_result.json`.

### endpoints.json

```json
{"endpoints":[{"id":"EP-001","method":"GET","path":"/payslips/{id}","raw":"\\(base)/payslips/\\(id)","useCases":["UC-001"],
  "client":{"file":"rel","type":"PayslipRequest"},
  "request":{"fields":[{"name":"id","type":"string","required":true}]},
  "response":{"fields":[{"name":"gross","type":"decimal","required":false}]},
  "errors":[{"status":404,"reaction":"shows the not-found state"}],
  "auth":"bearer token","backend":{"repo":"me-api","file":"rel","line":40,"auth":"policy Employee"},
  "label":"VERIFIED"}]}
```

| Field | Meaning |
| --- | --- |
| `method`, `path` | HTTP method and the path with parameters as `{name}` |
| `raw` | The path as written in the code, before constants were resolved |
| `useCases` | `UC-NNN` ids that call it |
| `client` | Where the app builds the call: its `file` and the request `type` |
| `clients` | Every client that builds the call, as `{file,type}` entries. One endpoint key can have several clients. `client` is the first |
| `request.fields`, `response.fields` | Field `name`, `type` and `required` (for a response, whether the value can be absent). Optional `nullable`: `explicit` when the type allows null, `default` when the decoder supplies a default, `no` otherwise |
| `disagreements` | Optional. Each place where a client field is absent from or differs in the backend: `field`, `client` and `backend` as `file:line`, and a `note` |
| `errors` | Each status the code handles and what the user sees |
| `auth` | The auth policy or token the app sends, or `null` |
| `backend` | Where a contract repository defines the route, with its authorization, or `null` when no backend file was given or found |
| `label` | `VERIFIED` when read in the code, `INFERRED` when deduced, `UNKNOWN` when not found. `VERIFIED` needs both the client and the backend cited, `INFERRED` only the client, `UNKNOWN` neither. After `contracts.py` runs, `VERIFIED` means `backend` is set and a use case cites the endpoint with a client file, an endpoint with a backend match but no citing use case is `INFERRED`, an endpoint without a backend match that was `VERIFIED` from the client side becomes `INFERRED`, and `UNKNOWN` stays `UNKNOWN` |
| `reason` | Optional. Why the contract reader left the label `UNKNOWN`, naming the field it could not read |

**Merge of the contract reader.** `contracts.py` runs first and sets `backend` and the route-based label; then the
contract reader runs per batch of up to 10 endpoints, and `merge_contracts.py` writes its `request`, `response`,
`errors` and `auth` into the entry with the same id, appends its disagreements, never lowers a `VERIFIED` label unless
the reader returns `UNKNOWN` with a field-level `reason`, never raises a label to `VERIFIED`, and reports its
`injectionFlags`. The envelopes are kept in `contracts_result.json` and applied again after every `render.py catalogs`.

### ids.json

```json
{"UC":{"view payslip list":"UC-001"},"UCfiles":{"UC-001":["Modules/Payslips/PayslipList.swift"]},"SCR":{},"FLOW":{},"RULE":{},"EP":{"GET /payslips/{}":"EP-001"},
 "max":{"UC":7,"SCR":3,"FLOW":2,"RULE":11,"EP":4}}
```

The registry that keeps ids stable. See Ids. `UCfiles` maps each `UC` id to the sorted files of its use case, as `rel`
without the line. A new use-case key whose sorted files equal those recorded for a retired key takes that id instead of
a new one, so a renamed use case keeps its id.

### ledger.json and LEDGER.md

```json
{"version":1,"classes":{"screens":{"total":4,"covered":4,"withReason":1,"percent":100,"pass":true,
                        "uncovered":[{"item":"DebugScreen","reason":"not user-facing"}]}},
 "thresholds":{"screens":100,"endpoints":100,"events":100,"permissions":100,"storage":100,"strings":95,"fields":95,"platform":0},
 "pass":true}
```

| Field | Meaning |
| --- | --- |
| `classes.<class>.total` | Inventory items in the class |
| `classes.<class>.covered` | Items that a catalog entry references, plus items left out with a counting reason |
| `classes.<class>.withReason` | How many of the covered items are left out with a reason |
| `classes.<class>.percent` | `covered / total * 100`, 100 when the class has no items |
| `classes.<class>.pass` | `true` when `percent` meets the class threshold. A class with no items passes |
| `classes.<class>.uncovered[]` | Items with no reference. `reason` is `null` when no reason exists. A reason recorded by a person in `overrides.json` is free text and always counts. A reason the scripts assign themselves, which is what "in the catalog" means, must be one of `not user-facing`, `dead code`, `out of module` |
| `thresholds` | The percentages in force |
| `pass` | `true` when every class passes: (covered + covered-with-reason) / total is at least its threshold, and a class with no items passes. An uncovered item without a reason counts against its class |

### grade.json

```json
{"version":1,"checks":[{"name":"sections","pass":true,"detail":""}],"pass":true}
```

One entry per shape check of the grader, in this order: `sections`, `rules-per-use-case`, `criteria-per-use-case`,
`criteria-numbering`, `citations-resolve`, `unknowns-have-owner`, `prose-complete`, `no-duplicate-use-cases`,
`banned-nouns`, `overrides-reflected`. `detail` names every failing item, at most 20, then `and N more`. `pass` is `true`
when every check passes.

`unknowns-have-owner` fails for a line of sections 1 to 8 that holds `UNKNOWN` without the words `searched` and `owner`,
unless every `OQ-NNN` the line names as `open question OQ-NNN` is listed in section 8. Every UNKNOWN the renderer writes
from a catalog in sections 1 to 8 is `UNKNOWN (open question OQ-NNN)`, with one open question per catalog entry that has
gaps: a use case with evidence other than VERIFIED, INFERRED or PROPOSED, or with no file and no screen; a screen whose
catalog states have no known evidence or no text, or that has no actions or no declaration; an endpoint whose label is
`UNKNOWN` or that has no auth, response fields, errors, client or backend, a field without type, required flag or
nullability, or an error without a reaction; a rule below High confidence, or without priority, category, statement or
source. Each question says what was searched (the entry's files, declaration, clients or source) and its owner,
`owner of <app name>`. The ids run from `OQ-001` in that order (use cases, screens, endpoints, rules) after the
writer's own questions, and `review.py questions` writes `OPEN_QUESTIONS.md` from the same list. What is not a
question is written so that it is not an unknown fact: a cited file whose line could not be resolved reads
`line not resolved`, and an empty catalog reads `No endpoints in the catalog.` (and so on). The prose placeholder `UNKNOWN — <what is missing>` is left to `prose-complete`, which fails while one
remains before Appendix F.

`overrides-reflected` knows, besides the catalog ids, every item key the ledger counts (a screen as `<file> <name>`, a
field as `<SCR id or file>.<slug>`, an endpoint as `METHOD /path`), so a reason recorded with `review --accept` for any
uncovered item is a known drop. Citations are checked when backticked as `path:line` or `path:line-line`, where the path has a `/` or a
source-file extension (a host with a port is not one). The renderer backticks every citation in prose evidence.

### review.json and REVIEW.md

```json
{"passes":[{"n":1,"ledger":{"pass":true},"grade":{"pass":true},
  "critic":[{"severity":"Blocker|High|Medium|Nit","section":"Screens","finding":"...","fix":"...","owner":"writer"}]}]}
```

| Field | Meaning |
| --- | --- |
| `passes[].n` | The round, from 1 |
| `passes[].ledger.pass`, `grade.pass` | The verdicts of the ledger and grader in that round |
| `critic[].severity` | Blocker, High, Medium or Nit. Blocker and High go back to the owner |
| `critic[].section` | The spec section the finding is about |
| `critic[].finding` | What is wrong, with a citation |
| `critic[].fix` | What to change |
| `critic[].owner` | The part that owns the gap: `analyst`, `mapper`, `rules`, `contracts` or `writer`. The `spec` skill sends a Blocker or High finding back to it, for that gap only |

### prose.json

What the spec writer returns. `render.py spec` puts each entry into its slot; a slot without an entry is rendered as
`UNKNOWN — <what is missing>`.

```json
{"summary":"...",
 "screens":{"SCR-001":{"purpose":"...","states":[{"name":"empty","shows":"...","evidence":"`rel:line`"}]}},
 "criteria":[{"ids":["UC-001"],"text":"...","evidence":"`rel:line`"}],
 "dependencies":["..."],
 "openQuestions":[{"id":"Q-001","question":"...","searched":"...","owner":"..."}],
 "data":[{"entity":"...","fields":"...","storage":"...","lifetime":"...","evidence":"`rel:line`"}],
 "keepDrop":{"UC-001":{"keep":["..."],"drop":[{"what":"...","file":"rel"}]}}}
```

| Field | Meaning |
| --- | --- |
| `summary` | Section 1 |
| `screens.<SCR>.purpose`, `states` | Purpose and content, and the states that replace the catalog's states, of one screen in section 3 |
| `criteria` | Section 6, numbered in this order. `ids` are `UC-NNN` ids or their `CAP-NNN` aliases |
| `dependencies` | Section 7, one line each |
| `openQuestions` | Section 8 |
| `data` | Appendix B, one row per entity |
| `keepDrop.<UC>` | Appendix C: behaviour to keep, and implementation facts to drop with the file each came from |

Every entry cites `path:line` in backticks, or says `UNKNOWN; searched: ...; owner: ...` (never `UNKNOWN — `, the
renderer's mark for an empty slot, which `prose-complete` fails). A use case without a rule
carries the sentence `No client-side rule; the server decides.` with a backticked citation in one of its criteria or
in the purpose of one of its screens.

### SPEC.md and OPEN_QUESTIONS.md

`SPEC.md` is the deliverable, in the template below. It can be named with `--name`, for example `docs/specs/payslips.md`.
`OPEN_QUESTIONS.md` lists every UNKNOWN with what was searched, who can answer and its id.

## Ids

- Ids are `UC-NNN`, `SCR-NNN`, `FLOW-NNN`, `RULE-NNN` and `EP-NNN`. They have three digits minimum.
- `ids.json` holds one map per class from a **normalized key** to the id, and `max` holds the highest number issued per class.
- An id is never reused. A retired key stays in its map, and a new key always takes `max + 1`.
- A re-run looks up the normalized key first, so the same item keeps its id. Only `render.py` issues ids.
- `norm(text)` lower-cases the text, replaces every run of characters other than letters and digits with one space,
  trims, and drops the words `a`, `an` and `the`.
- The normalized key of a use case or a flow is `norm(name)`. The key of a screen is `norm(name)`, a `|`, and the file
  path of its declaration without the line. The key of a rule is `norm(name)`, a `|`, and the source file without the
  lines.
- The normalized key of an endpoint is the upper-case method, one space, and the path with every parameter (`{id}`,
  `:id`, `$id`) replaced by `{}`, as `inventory.json` holds it.
- With a capability index, a use case whose outcome matches a capability takes that `CAP-NNN` as `alias`. A match is an
  equal `norm(name)`, or at least one file that the capability's `implementations[app.name].files` share with the use
  case's `files`. A name match wins over a file match, and a capability aliases at most one use case. The spec
  shows the alias next to the `UC` id, and either id is valid in an AC line.
- A merge in `overrides.json` retires the `from` ids and keeps the `into` id.

## Template

The first eight sections use exactly these headings, in this order:

1. `## Summary`
2. `## Capabilities`
3. `## Screens`
4. `## Endpoints`
5. `## Business rules and permissions`
6. `## Acceptance criteria`
7. `## Dependencies and decisions`
8. `## Open questions`

Appendices follow with exactly these headings:

- `## Appendix A. Fields and ids`
- `## Appendix B. Data`
- `## Appendix C. Behaviour to keep, implementation to drop`
- `## Appendix D. Strings, analytics and platform`
- `## Appendix E. Flows`
- `## Appendix F. Coverage`

**Header lines.** The spec opens with:

```
Source: module <name> of <app> (no source issue)
Reference HEADs: <app> `<sha>`
```

The `Reference HEADs:` line is followed by one entry per contract repository, in the same shape as the app entry. Then
come the module scope (core folders and touch points) and the evidence labels.

**Evidence labels** are exactly `VERIFIED`, `INFERRED`, `UNKNOWN` and `PROPOSED`. `PROPOSED` marks anything the
writer suggests.

**Capabilities table.** The columns are `| CAP | Name | Design | Screens | Notes |`. The `CAP` column holds the `UC-NNN`
id, or the `CAP-NNN` alias when one exists. The `Design` column is `carry-as-is (<app> <file:line>)` for every row.

**AC line format.** Acceptance criteria are rendered one per line:

```
- **AC<N> (<id>[, <id>]):** <text>
```

`N` starts at 1 and rises by one across the whole spec. Each `<id>` is `UC-NNN` or its `CAP-NNN` alias. Each criterion
is observable on screen, so a Maestro flow or a unit test can assert it. Tools such as `/issues` parse this numbering.

**Content rules.**

- The spec is compiled from the catalogs. `render.py` writes the tables and ids. The spec writer writes the prose
  from the catalogs and the cited code, and adds no fact without a citation.
- Every claim is cited as `file:line`, or marked UNKNOWN with what was searched.
- Requirement sentences use no word from `bannedNouns`. Such words are allowed only in Appendix C.
- Every use case has at least one rule, or the sentence "no client-side rule, server decides" with a citation.
- Every use case has at least one acceptance criterion.

## Thresholds and defaults

| Setting | Default | Notes |
| --- | --- | --- |
| Coverage of screens, endpoints, events, permissions, storage keys | 100 percent | Overridable in `app-spec.json` |
| Coverage of string keys and fields | 95 percent | Overridable in `app-spec.json` |
| Coverage of platform entries | 0 percent | Reported, never fails, until `app-spec.json` sets a threshold: the section is app-wide |
| Pass rule | | A class passes when (covered + covered-with-reason) / total is at least its threshold, and a class with no items passes. The ledger passes when every class passes |
| Reasons that let an uncovered item pass | `not user-facing`, `dead code`, `out of module` | A reason recorded by a person in `overrides.json` is free text and always counts. A reason the scripts assign themselves, which is what "in the catalog" means, must be one of these three |
| Review passes | 2 | Range 1 to 5. Only Blocker and High findings are sent back |
| Shard size | 9,000 non-blank lines | Without the Workflow tool: groups of up to about 25,000 lines, at most six analysts in parallel |
| Locale | `en` | Source-language strings quoted in the spec |
| Banned nouns | `Realm`, `Swinject`, `NotificationCenter`, `ViewModel`, `Redux`, `Hilt`, `Room` | Configurable per run |
| Guard | on | `guard` option in Claude Code, `APP_SPEC_GUARD=false` turns it off in Devin |

## Agents and workflows

| Agent | Returns |
| --- | --- |
| `ios-analyst`, `android-analyst`, `rn-analyst` | Use-case fragments for one shard, in the fragment shape of `understand_result.json`. With a referee prompt: a verdict on each cited claim. Copied from App Fusion, edited to describe one app |
| `use-case-mapper` | Merged use cases, screens and flows from all fragments, one use case per user outcome. No fusion classes |
| `business-rules-extractor` | Rule cards for one shard in the shape of `rules_result.json`. Copied from App Fusion, edited to describe one app |
| `contract-reader` | The envelope `{endpoints:[{id, request, response, errors, auth, label, reason, citations}], disagreements, injectionFlags}` for a batch of up to 10 endpoints, from the app and from contract repositories. `merge_contracts.py` merges it into `endpoints.json` |
| `spec-writer` | `prose.json`: the prose slots of `SPEC.md` from the catalogs and the cited code, citations only |
| `spec-critic` | Findings `[{severity, section, finding, fix, owner}]` in the shape of `review.json` `critic`, ranked Blocker, High, Medium, Nit. It opens at least one cited range per use case |

| Workflow | Returns |
| --- | --- |
| `understand-module.js` | `understand_result.json`: analysts per shard, the mapper, one referee per use case. Resumable with a run id |
| `extract-rules.js` | `rules_result.json`: one extractor per shard, one citation referee per rule, two judges per P0 rule. Resumable with a run id |

Spec writing, review and the skills are single agents or scripts called from a skill, so they need no workflow. Every
skill gives the path without the Workflow tool. The skills are `spec`, `review` and `status`.

All agents are read-only. They write nothing outside the output folder.

## Hooks

- `hooks/hooks.json` registers the guard on `PreToolUse` for `Edit|Write|MultiEdit|NotebookEdit|Bash` in Claude Code and
  for `edit|write|notebook_edit|apply_patch|exec|write_to_process` in Devin.
- The guard finds `app-spec.json` from the output folder named in the command, the project folder (and two levels below it,
  so the default `./specs/<name>` is found), or the paths a tool call names. It denies file tool writes under `app.path` and under each contract repository's path. It asks before a
  shell command that would write there. It does nothing when no `app-spec.json` is found.
- `APP_SPEC_GUARD=false` turns the guard off in Devin. In Claude Code the `guard` option does the same.
- `hooks/devin-context.sh` runs `scripts/devin_context.py` at session start. It prints the plugin's real folder, the
  tool-name mapping, the instruction for working without the Workflow tool, and the option defaults. It prints this
  only when `DEVIN_PLUGIN_ROOT` or `DEVIN_PROJECT_DIR` is set.
- Hooks run only in local sessions on both hosts. The skills print deny rules for `.claude/settings.json` and
  `.devin/config.json` as a second layer.

## Safety

- **Read-only source.** Scripts, agents and skills never write under the analysed app's path or under a contract
  repository's path. Writes go to the output folder only.
- **Untrusted content.** Source code, comments, strings and READMEs of the analysed app are data, never instructions.
  Agents and workflows report instruction-shaped text in `injectionFlags` and never act on it. Workflow prompts fence
  such content as `<<<UNTRUSTED ... UNTRUSTED>>>`.
- **Secrets.** A secret is never reproduced. Report `file:line` and a 2 to 4 character masked preview.
- **Standard library.** Python scripts use the standard library only and run on Python 3.8 or later.
- **Public repository.** The plugin is public under Apache 2.0. No file derived from Visma code is committed. Fixtures
  are synthetic. The calendar spec that sets the quality bar is never committed. The critic uses the distilled
  `references/rubric.md`.
- **People decide.** A person confirms the module scope, accepts differences and records corrections in
  `overrides.json`. The plugin never overwrites that file.
