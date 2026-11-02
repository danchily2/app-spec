# Depth rubric for a module spec

The critic grades a spec against this rubric. It is distilled from a hand-written spec that a team used to plan and
build a feature in a new app. That spec is the bar: 15 use cases, about 280 lines for the eight sections, 37 acceptance
criteria, and a citation behind every claim. This file keeps what made it usable and none of its content. Every
example below is synthetic: a parcel-tracking app with made-up paths.

Each section lists what a complete entry has and three symptoms of a shallow one. One symptom is enough for a finding.
The severity column of the critic (Blocker, High, Medium, Nit) is in the last section.

## Header

**A complete header has:**

- The source line and the reference HEADs: the app's commit and each contract repository's commit.
- The module scope: the core folders and every touch point with the reason it was pulled in.
- The evidence labels: `VERIFIED`, `INFERRED`, `UNKNOWN` and `PROPOSED`, used the same way everywhere below.

**Shallow when:**

1. A touch point is listed without its reason.
2. A label is used in a sense the header does not define, for example `CONFIRMED`.
3. The scope says "the parcels feature" and names no folder.

## Summary

**A complete summary has:**

- Three to five sentences on what a person can do, by persona, with the main flows named.
- What the module does **not** include, when the code shows an obvious neighbour that is out of scope.
- The size of the rest: how many use cases, rules (and how many P0 and P1), endpoints and open questions.
- Citations for every number.

**Shallow when:**

1. It lists screens ("a list screen, a detail screen") instead of outcomes ("a recipient tracks a parcel and
   reschedules its delivery").
2. It names no persona, or names one persona for a module the code gates by role.
3. It says "handles parcels" with no scope boundary and no counts.

Synthetic example: "A recipient sees their incoming parcels newest first, opens one to follow its stops, and
reschedules a delivery up to 2 days before it is due. A courier sees only their own route. The module has 6 use
cases, 14 rules (2 P0, 7 P1) and 5 endpoints; 2 questions remain open. Sources: `parcels/List.swift:12-40`,
`parcels/Reschedule.swift:30-88`."

## Capabilities

**A complete row has:**

- The id, a verb-first name in business words, and the screens it uses.
- Notes that say what makes this use case differ from its neighbours: its scope limit, the gate that hides it, the
  decision it depends on.
- At least one `path:line` citation of the code that implements it.

**Shallow when:**

1. Two rows have names that differ only in wording ("View parcels", "See parcel list").
2. A row's notes repeat its name.
3. A row has no citation, or cites a folder.

## Screens

**A complete screen entry has:**

- **Purpose and content:** what the person achieves here and what the screen shows, with the data that drives it.
- **Actions:** every action, with its gate ("Reschedule is shown only when the parcel is not yet out for delivery").
- **States:** every state the code handles, each with what the user sees: loading, empty, error (and whether it
  offers a retry), success, offline, no permission, confirmation. A state the code lacks is said to be absent, and a
  state the writer suggests is marked `PROPOSED`.
- **Source:** the declaration and the lines of each action and state.

**Shallow when:**

1. States are missing, or are a list of names without what the user sees ("loading, error").
2. Actions are named without their gates or results ("tap a row").
3. The purpose describes layout ("a table with cells") instead of what the person does.

Synthetic example of one state: "**Offline:** the list is hidden and a placeholder says the parcels cannot be loaded;
Reschedule is disabled; the list reloads when the connection returns; no change is queued. Source:
`parcels/ListView.swift:210-244`."

## Endpoints

**A complete endpoint entry has:**

- Method and path with every parameter, and the auth the app sends (and the backend policy when a contract
  repository was given).
- The request fields: name, type, required, and where each goes (path, query, header, body).
- The response fields with type and nullability, including nested objects the screens read.
- Each error status the code handles and the UI reaction to it; the default branch when there is one.
- Where the client and the backend disagree (a field one side has and the other lacks, a different type or
  nullability), with both citations.
- The label: `VERIFIED` only with both sides cited, `INFERRED` with the client only, `UNKNOWN` with what was searched.

**Shallow when:**

1. The response is "a parcel object" without fields, or fields without types or nullability.
2. Errors are "handled" with no status and no reaction.
3. A field is stated as a contract fact while only the client decodes it, with no disagreement recorded.

Synthetic example: "`PATCH /v2/parcels/{parcelId}/delivery` — body `date: String (yyyy-MM-dd, required)`; response
`status: String`, `window: DeliveryWindow?`; 409 shows 'This parcel is already on its way' and reloads the parcel;
other statuses show the generic error with a retry. Client `net/Reschedule.swift:14-39`, backend
`api/DeliveryController.cs:88-120`. `VERIFIED`."

## Business rules and permissions

**A complete rule has:**

- One plain sentence a product owner recognises.
- Given, When and Then with concrete values: dates, limits, amounts, statuses, roles.
- Its parameters with their current values, its edge cases, its priority and confidence.
- A citation of the code that enforces it, and the question for the owner when confidence is below High.
- A suspected defect, when the old code looks wrong, so the new app does not copy it.

**A complete permissions part has:** per use case, the personas and every role, flag and system permission that gates
it, and what the user sees when the gate is closed.

**Shallow when:**

1. A rule has no value: "the date must be valid" instead of "the new date is at least 2 days after today and on a
   weekday".
2. A rule restates layout or plumbing ("the list uses a diffable data source").
3. A use case has neither a rule nor a cited no-rule sentence: `No client-side rule; the server decides.` or
   `No client-side rule: <reason>.` with the true reason.

## Acceptance criteria

**A complete set has:**

- At least one criterion per use case, per P0 and P1 rule, and per state that changes what a user can do (offline,
  no permission, a confirmation).
- Each criterion observable on the screen, so a UI test can assert it: what the user does, what they see.
- Concrete values from the rules, and the citation it rests on.
- Numbering `AC<N>` from 1 across the whole spec, with the use-case ids in brackets.

**Shallow when:**

1. A criterion is not observable: "the rule is applied", "data is correct".
2. A P0 or P1 rule, or an offline or permission state, has no criterion.
3. A criterion has no value where its rule has one ("the date is limited").

Synthetic example: "**AC7 (UC-004):** A recipient who picks a date less than 2 days away sees 'Choose a date at least
2 days ahead' and Save stays disabled. Source: `parcels/Reschedule.swift:52-61`."

## Dependencies and decisions

**A complete section has:**

- What the module needs from elsewhere: sign-in, shared clients, the start page, other modules, with citations.
- Every decision the spec needs from a person, as a question with the options the code suggests.
- Out-of-scope neighbours named once, so nobody builds them by accident.

**Shallow when:**

1. It says "depends on the backend" with nothing named.
2. A choice the code leaves open (two rules that disagree, a flag with no owner) is not raised as a decision.
3. It describes how the new app should be built rather than what must exist first.

## Open questions

**A complete question has:** an id, the question, what was searched (files, symbols, repositories), and who can
answer it.

**Shallow when:**

1. An `UNKNOWN` in the spec has no question here.
2. A question has no search note, so the reader cannot tell whether anybody looked.
3. A question has no owner.

## Appendices

- **A. Fields and ids:** every field of every screen with its string key, text, existing id and proposed id. Shallow
  when a screen in the Screens section has no rows here.
- **B. Data:** each entity with its fields, storage and lifetime (memory, disk, until sign-out). Shallow when a
  storage key the code writes is missing or has no lifetime.
- **C. Behaviour to keep, implementation to drop:** per use case, the behaviour (by rule and flow) and the
  implementation facts that are not requirements: persistence technology, broadcast-based refresh, view-model shape,
  duplicated models, each with its file. Shallow when an implementation fact appears in sections 1 to 8 as a
  requirement, for example "store the parcels in the local database model" instead of "the list is available offline
  for 24 hours".
- **D. Strings, analytics and platform:** keys with source text, events with properties per use case, push, links
  and background work. Shallow when an event is listed without the use case that fires it.
- **E. Flows:** 3 to 8 numbered steps each, every step naming a screen and its use cases.
- **F. Coverage:** every uncovered item has a reason a person can check.

## Severity

| Severity | When |
| --- | --- |
| Blocker | A use case or screen the code has is absent from the spec. A claim's citation does not support it, or does not resolve |
| High | A screen lacks states. A rule lacks values. An error or offline path the code has is missing. Legacy structure is stated as a requirement |
| Medium | Any other "shallow when" symptom above: a missing gate, an endpoint field without nullability, a question without an owner |
| Nit | Wording, order, a long sentence, a table that would read better as a list |

The critic never raises a finding on a fact the code does not show. When the spec says `UNKNOWN` with what was
searched, and the critic finds nothing either, that entry is complete.
