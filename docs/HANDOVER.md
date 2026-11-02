# app-spec handover: fix loop after the payslips runs (2026-11-02)

Brief for the agent that continues work on the app-spec plugin. Read it all before you change anything.

## The task

Make the plugin produce a spec that passes its own checks on a real module, without manual fixes during the run.
Work in a **loop**. Each round fixes a group of major issues, makes a release, reruns the test suites and the
payslips acceptance run, and assesses the result. Stop only when the exit criteria below are met. Do not stop after
one round because "it looks better".

## Where things are

| What | Where |
|---|---|
| Plugin repo (local only, no remote) | `~/Documents/GitHub/app-spec`, plugin folder `plugins/app-spec` (below: `P/`) |
| Current work branch | `fix/run2-quality-gates`, 10 fix commits on top of `v0.2.0` (`37af55f`), not merged, not released |
| Change log of the branch | `P/CHANGELOG.md`, section `## Unreleased` |
| Design | `P/docs/DESIGN.md` |
| Source app (read-only) | `~/Documents/GitHub/visma-scarlet/sources/me-ios` |
| Contract repo (read-only) | `~/code/me-api` (shallow clone of `Visma-Mobile-Employee/me-api`) |
| Capability index | `~/Documents/GitHub/visma-scarlet/analysis/work-app/capabilities.json` |
| Run 1 output (v0.1.0, manual cleanup) | `~/Documents/GitHub/vmm3/specs/payslips/` and its `PLUGIN_FIXES.md` |
| Devin run 2 register (v0.2.0) | `~/Downloads/PLUGIN_PROBLEMS.md` (P1–P40, N1–N6) |
| v3 output (branch code) | `~/Documents/GitHub/vmm3/specs/payslips-v3/` (`payslips.md`, `REVIEW.md`, `critic-1.json`, `critic-2.json`, `OPEN_QUESTIONS.md`) |

## Rules

- Change only the plugin repo. Never write under the source app or the contract repo.
- One fix per commit. Each fix gets a test that fails without it. Never weaken or skip a test to make it pass; if a
  test fixture is wrong (it happened once: a fixture range past the end of its file), correct the fixture and say so
  in the commit.
- Add a line to `## Unreleased` in `P/CHANGELOG.md` for each fix, in plain words, with the run evidence that found it.
- Commit messages end with the co-author trailer the session gives you.
- Two-strikes rule: if a fix fails twice, stop and write down the root cause before a third attempt.
- Environment notes for this machine:
  - The Bash sandbox writes only inside the current project. Edits in `~/Documents/GitHub/app-spec` need the sandbox
    off, or use the file Edit/Write tools.
  - `git commit` needs the sandbox off.
  - A pipelock hook blocks `rm -rf`; move a folder away instead.
  - Node 22: run `node --test tests/workflows.test.mjs` from `P/`. A folder argument after `--test` does not work.
- Agent definitions (`P/agents/*.md`) load when a session starts. After you change one, run the acceptance step in a
  **new** session, or the old prompt is used. Load workflows by `scriptPath` so the current file runs.

## The loop

Repeat these steps until the exit criteria are met.

1. **Pick the round.** Take the highest-ranked open items from the backlog below, about 3 to 6 that share a cause or
   a file. Write the round's list at the top of this file under "Round log".
2. **Fix.** One commit and one test per item, as in the rules.
3. **Test.** From `P/scripts`: `python3 -m unittest discover -s tests -q`. From `P/`:
   `node --test tests/workflows.test.mjs`. Both must pass. Baseline at handover: 366 Python, 29 Node, all passing.
4. **Release.**
   1. Merge the branch into `main` (fast-forward, or a merge commit if `main` moved).
   2. Bump the version in `P/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, as in commit `37af55f`.
      Use a minor bump (0.3.0, 0.4.0, ...) for a round with behaviour changes, a patch bump for fixes only.
   3. Rename `## Unreleased` in `P/CHANGELOG.md` to `## X.Y.Z - <date>` and start a new empty `## Unreleased`.
   4. Commit `release: app-spec X.Y.Z` with a one-paragraph summary, then tag `vX.Y.Z`.
   5. Do not push. The repo has no remote; publishing is Dan's decision.
   6. Start the next round on a new branch from `main`.
5. **Rerun the acceptance run** in a new session, with the released code, into a new folder (`payslips-vN`):

   ```text
   /app-spec:spec ~/Documents/GitHub/visma-scarlet/sources/me-ios \
     --capabilities ~/Documents/GitHub/visma-scarlet/analysis/work-app/capabilities.json \
     --scope CAP-029,CAP-080,CAP-225,CAP-226,CAP-227,CAP-231 \
     --module Modules/PayslipsFeature \
     --contracts ~/code/me-api \
     --out ~/Documents/GitHub/vmm3/specs/payslips-vN --name payslips.md
   ```

   Take every proposal as the skill offers it. Do not fix anything by hand during the run. If the run needs a manual
   step, stop and record it: a manual step is a plugin defect and goes into the backlog.
6. **Assess.** Fill a new row of the scorecard below from the run's `review.json`, `ledger.json`, `grade.json`,
   `endpoints.json`, `rules.json` and `render-warnings.json`. Compare with the previous rows. For each remaining
   Blocker or High finding and each manual step, decide: plugin defect (add it to the backlog, ranked) or spec
   content that the review loop should have fixed (also a plugin defect if the loop could not fix it).
7. **Decide.** If the exit criteria are met, stop and write the final summary at the top of this file. Otherwise go
   to step 1.

If Devin is available, also run step 5 in Devin from a clone of the release tag (Devin's plugin cache stays on old
versions, see N1) and add its row to the scorecard. Devin runs all roles in one agent (N2), so its P0 judges are
not independent.

## Exit criteria

Stop the loop only when one payslips run on a released version meets all of these, with no manual step during the run:

- `grade.py` passes.
- `ledger.py` passes, or every failing item has a reason a person could accept, and no failing item is a defect of the
  inventory or the ledger.
- The last review pass has 0 Blocker and 0 High findings.
- No `render-warnings.json` entry of kind `citation`, and no entry that comes from a plugin defect.
- Every endpoint is `VERIFIED` or has a stated reason why it cannot be.
- Every in-scope capability (CAP-029, 080, 225, 226, 227, 231) has at least one use case and its rules.
- Both test suites pass.

Then do one confirming run on a second module (for example the calendar module, against the existing
scarlet-team-c calendar spec as the bar) to check that the fixes did not overfit payslips.

## Scorecard

| Run | Plugin | Touch points | Use cases (off-module) | Endpoints matched / `VERIFIED` | Rules (P0) | Grade | Ledger | Blocker / High left | Manual steps |
|---|---|---|---|---|---|---|---|---|---|
| 1 | v0.1.0 | 486, filtered by hand to 33 | 31 (15, removed by hand) | 0/12 / 0 | 121 (2) | pass | fail, screens 16/35 | 1 / 0 | 6 |
| 2 (Devin) | v0.2.0 | 21 | 11 (0) | 9/9 / 1 | ~30 (1) | fail | fail, screens 26/28 | 2 / 0 | N3 approvals |
| v3 | branch `2ab0bd1`→`a1c1138` | 31 | 11 (0) | 9/9 / 5 | 85 (0) | pass | fail, fields 51/58, strings 0/1 | 0 / 2 | 5 plugin fixes made mid-run, 1 rule path patched by hand |
| v4 | 0.4.0, headless, **partial** (usage limit hit after pass 1, $55.84) | 31 | 11 (0); 32 out of scope | 9 / 5 (4 INFERRED, not in inventory) | 87 (2); 84 referee corrections | fail (1 citation past end of file) | fail, fields 84.9%, strings 0/1 | 1 / 3 after pass 1 (pass 2 never ran) | 0 by hand; 1 denied workaround (transcript grep to save a contract batch) |
| v5 | 0.5.0, headless, 2 passes, $72.66 | 37 | 10 (0); all 6 in-scope caps | 11 / 6 (4 reached through a service stay INFERRED, no reason) | 162 (2): duplicates from the rules re-run | fail: bare file names + `ViewModel` | fail, strings 58.7% (19 start-page keys) | 2 / 3 after pass 2 (4 of 5 are rule findings pass 1 already raised) | 1 kind, 3 times: large answers stored as files (fixed in Round 4) |

## Backlog, ranked

Fix in this order unless a later run shows a higher-impact defect. Ids P-n and N-n refer to the Devin register.

### Round 1: defects the v3 run found (start here)

1. **A fix reaches only one owner.** Critic-1 sent the silent year-end failure to the writer. The writer fixed the
   screen and the criterion, but EP-007 (contracts) still describes the alert, and critic-2 raised it as High.
   Fix: in step 7.5 of `P/skills/spec/SKILL.md`, when a finding names a behaviour, also send it to every other owner
   whose section states that behaviour (screens, criteria, endpoint reactions, rules). Or give the critic a field
   `alsoAffects: [sections]` and route by it.
2. **Changing a rule's source changes its id.** `ids.json` keys a rule by name plus source file
   (`P/scripts/speclib/ids.py`, `render.py _rule_key`). Correcting a source path made RULE-073 into RULE-117, and the
   spec kept references to RULE-073 (critic-2, Medium). Fix: when a patch replaces a rule with the same name and the
   old source file is a suffix, prefix or the same file of the new one, keep the old id. Add a test with a
   module-relative path corrected to a full path.
3. **The out-of-scope list keeps items the core shard covered.** Touch-shard analysts put year-end reports, the FAQ
   link and analytics in `outOfScope` with "leave it to the core shard"; the core shard then made them use cases, but
   `foldOutOfScope` in `P/workflows/understand-module.js` (line ~391) removes an entry only when the name matches
   exactly ("Learn why I have no payslips (CAP-231)" vs "Learn why I have no payslips"). Rules too
   (RULE-007, 013, 029-031). Fix: match by normalized name with parenthetical suffixes removed and by overlap of cited
   files; drop an out-of-scope entry whose files or name match a kept use case or rule. Same in `extract-rules.js`.
4. **Partial paths in agent citations.** A rules extractor cited `Features/Main/MainPayslipFeature.swift:251-254`,
   relative to the module, not the app root. The range check reports it, but nothing fixes it. Fix:
   `speclib/paths.relative_path` resolves a path that matches the end of exactly one real file to its full path;
   apply it in `render.py catalogs` to rule sources and use-case files, as `merge_contracts.py` already does for
   envelopes.
5. **Rules review cannot correct, only remove (P18).** The referee schema is `{real, badEvidence, reason}`. RULE-091
   (Offset is the page size, not an offset) passed the referee and the critic had to raise it. Fix: add
   `correction: {field, value, citation}` to `VERDICT` in `P/workflows/extract-rules.js` (and `VERDICT_SCHEMA` in
   `understand-module.js`), and apply the correction in the workflow instead of only keeping or dropping the entry.

### Round 2: inventory discovery (register group B)

6. **P6: `S.*` string keys give 0.** me-ios uses a generated `S` enum (`EmployeeServices/EmployeeResources/.../Strings.swift`)
   over `Localizable.xcstrings`. `module.py string_keys_for` and `speclib/ios.py` only see literal keys. Map `S.foo.bar`
   accessors to their catalog keys through the generated file.
7. **P14: events give 0.** The payslip events are cases in `Modules/SnowplowAnalytics/.../Events.swift` and are sent
   through `AnalyticsFeature`. Extend the iOS event scan to enum cases sent by `SnowplowService`/`track` calls, and
   count events a core file sends, not only events a core file declares.
8. **P11/P21: endpoints built in a service are missed, so `Client: UNKNOWN`.** `allpayslips`, `allreports` and the
   report detail are built by string concatenation in `PayslipService.swift` and `ReportsService.swift`. Extend the
   path scan to `"\(base)/employees/\(id)/allpayslips?..."`-style builders and record the function as the client.
9. **P10/P26: route casing.** `normalize_endpoint` lowercases the path, and the spec shows the lowercased form
   (`exportfromalltenants`). Keep the original spelling for display and use lowercase only for matching.

### Round 3b: defects the v4 run found

19. **Range past the end of a file by a few lines** (`PayslipsListCoordinator.swift:25-124`, 123 lines) fails the
    grade. Clamp the end of an agent's range to the file's length in `render.py catalogs` when the start is inside it.
20. **Path completion reads only `source`.** `ViewModel/ViewModel.PayslipItem.swift:12-36` in a rule's other fields
    stayed partial. Complete paths in every string field of use cases, screens and rules.
21. **Touch-shard extractors put rules of kept use cases out of scope.** Four `scope` warnings: year-end rules in
    `ReportsService.swift` were dropped. With a use-case index, a touch-shard rule that serves an indexed use case
    goes into rules with that use case.
22. **Coordinators become screens** (critic-1 High, SCR-015 to SCR-018). A mapped screen whose file holds only an
    inventory coordinator, and no inventory screen, is not a screen.
23. **No clear way to save an agent's answer.** The run grepped subagent transcripts for the contract batch (denied).
    State in the skill how the answer reaches `save_json.py` (write it with the Write tool, then save).
24. **84 of 87 rules corrected by referees.** Check whether the referees rewrite text that was right.

### Round 5: defects the v5 run found

25. **A `rules` finding cannot be fixed.** Step 7.5 re-runs the extraction on the shard; the new cards get new
    source keys, so `patch_result.py` adds them beside the old ones (87 -> 162 rules, pairs such as RULE-031/125),
    and the wrong old cards stay. Give the rules owner the finding and the named cards and take back corrected cards
    with the same name and source, plus `remove`.
26. **Endpoints reached through a service stay INFERRED.** A use case cites `ReportsService.swift` (the endpoint's
    `usedBy`), not the request file, so the label is never VERIFIED and the endpoint has no reason.
27. **The grader does not resolve a bare file name** that exactly one file has, while the catalog check does.
28. **Strings of the start page** (in core because of the Salary card) fail the strings class: a person reason, or
    count only keys a kept screen or use case uses.

### Round 3: agent and schema consistency (group C)

10. **P16:** `P/agents/use-case-mapper.md` says `flags`; the schema field is `injectionSuspects`. Make them agree.
11. **P23:** rules schema has free-text `useCase` and no conflict field. Use the use-case id from `use-cases.json`
    and add `conflictsWith`.
12. **P9:** analyst and critic prompts say read-only, but the path without the Workflow tool needs them to write
    files. State which roles write what, where.
13. **P27:** `CLAUDE.md`/`AGENTS.md` inside the analysed repos are reported as injection flags. Exclude agent
    configuration files from analysis, or report them as "agent config, not followed" instead of injection.

### Round 4: sharding (group D)

14. **P5, P12:** shards group unrelated files under names like `[EmployeeServices/Payslips..Modules/EmployeeAppCore]`.
    Group by feature folder and keep a shard to one area; never mix `Package.swift` files of three packages.

### Round 5: Devin runtime (group E, plugin side only)

15. **N1:** record the plugin version and git SHA in `app-spec.json` and print them at the start of a run.
16. **N2/P3/P24:** without the Workflow tool, record `independence: single-agent` and label P0 rules "single judge"
    in the spec and the report.
17. **P20/P22:** ship a runner for the path without the Workflow tool (Devin wrote one: ask Dan for
    `~/app-spec-pilot/run2/tools/` from the Devin machine) so the workflows run without a hand-written driver.
18. **N3:** not fixable in the plugin (Devin's exec approval inside scripts). Document the allow-list Devin needs.

### Already fixed on the branch (verify, do not redo)

P29 (`30ebb52`), P30 (`2b241e2`), P38/N4/N6 (`9a1cc5a`, `6b2348b`), N5 (`52de99d`), P39 (`2ab0bd1`, `6d02be4`),
endpoint notes (`7fedb33`), sub-view coverage (`a4d32e8`), out-of-scope banned nouns (`a1c1138`). The register
marks P4, P7, P13, P15, P25, P28, P31, P33, P36, P40 fixed in v0.2.0.

## Round log

Add one entry per round: date, items, commits, release tag, run folder, scorecard row, decision.

- **Round 0 (2026-11-02, this handover):** 10 commits on `fix/run2-quality-gates`, not released. v3 run in
  `~/Documents/GitHub/vmm3/specs/payslips-v3`. Next: release these commits as 0.3.0, then start Round 1.
- **Release 0.3.0 (2026-11-02):** branch fast-forwarded into `main`, `release: app-spec 0.3.0` = `d8232fd`, tag
  `v0.3.0`. Not pushed (the repo now has a remote `origin` = `danchily2/app-spec`, `main` is ahead of it).
- **Round 1 (2026-11-02):** branch `fix/round1-review-routing`. Items: (1) a fix reaches every owner, (2) a rule
  keeps its id when its source path is corrected, (3) the out-of-scope fold matches by normalized name and files,
  (4) partial paths in agent citations resolve to full paths, (5) referees can correct, not only remove (P18).
  Commits: `c97bd27` (4, `paths.complete`), `77278fb` (2, `render._rule_id`), `0268ac9` (3, `_core_name` in both
  workflows + range-overlap fold in `render.py`, new `scope` warning kind), `7f2f8dd` (5, `corrections` in both
  verdict schemas, new `corrected` result field), `34050c6` (1, critic `alsoAffects` + `review.py route`, step 7.5
  uses it). Tests: 370 Python, 33 Node, all pass. Two Node stats tests gained `corrected: 1` because the harness
  sample referee fills every schema field (a new key, not a weaker check). Released as **0.4.0** (`c3758ae`, tag
  `v0.4.0`), not pushed.
  Not done: step 5 (the payslips-v4 acceptance run) and steps 6-7. The installed plugin in
  `~/.claude/plugins/installed_plugins.json` is still **0.1.0** (cache from 2026-10-31); update it to 0.4.0 before the
  run, or the run tests old code. Next: in a new session, update the plugin, run step 5 into
  `~/Documents/GitHub/vmm3/specs/payslips-v4`, fill the scorecard row, then pick Round 2.
  Update: Dan updated the plugin to 0.4.0 (cache at `24c1f55`). The v4 run started as a headless new session
  (`claude -p '/app-spec:spec ... --headless'`, script and stream log in the session scratchpad), so no person
  answered the scope question; the report says so.
- **Round 2 (2026-11-02, in parallel with the v4 run):** branch `fix/round2-inventory`, items 6-9 (group B). The v4
  inventory (0.4.0) showed all four again: 5 endpoints (no `allpayslips`, `allreports`, report detail), 0 events,
  7 strings. Commits: `cb10c6d` (9, `display` path in the app's spelling), `4b35743` (8a, URLs a Swift service
  builds with `+`, client `url-builder`), `1711b61` (8b, request types a core file calls, or a called service
  function calls, kept as touch with `usedBy`), `bb5d795` (6, `S.*` accessors resolved to catalog keys),
  `48ac365` (7, event-enum cases a core file sends). Checked on a copy of the v4 folder: 12 endpoints (all three
  missing ones found; 2 Dottie start-page endpoints; no false ones after two narrowing passes), 46 string keys,
  6 events. Tests: 375 Python, 33 Node. Not released yet: release as 0.5.0 after the v4 assessment.
- **v4 assessment (2026-11-02):** the run stopped on the account's 5-hour usage limit while it routed the pass-1
  findings; pass 2 never ran, so the Blocker and 2 of the 3 High are spec content the loop had already routed. The
  findings use `alsoAffects` as intended. New plugin defects are items 19-24 (Round 3b). Exit criteria not met. Group
  C items done so far: P16 (`4680efb`), P27 (`c5b0b98`) on `fix/round3-agent-schemas`.
- **Release 0.5.0 (2026-11-02):** Rounds 2, 3 (P16, P27) and 3b (items 19-24) fast-forwarded into `main`,
  `release: app-spec 0.5.0` = `7acf3a7`, tag `v0.5.0`, pushed to `origin`. Tests: 380 Python, 35 Node. Installed
  plugin updated to 0.5.0 with `claude plugin marketplace update app-spec` + `claude plugin update app-spec@app-spec`.
  v5 run started headless into `~/Documents/GitHub/vmm3/specs/payslips-v5`. Still open in group C: P23 (rule use-case
  id and `conflictsWith`), P9 (which roles write what). Then groups D (sharding) and E (Devin runtime).
  Cost note: v4 used $55.84 before the account's 5-hour limit stopped it; a full run with two passes costs more.
- **v5 attempt 1 (2026-11-02):** stopped after the inventory. Headless print mode waits only 10 minutes for a
  background workflow after the turn ends, then kills it (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). Not a plugin
  defect; the runner now sets the variable to 0. Folder kept as `payslips-v5-aborted`. Its 0.5.0 inventory confirms
  Round 2: 11 endpoints (allpayslips, allreports, report detail found), 6 events, 46 string keys (v4: 5, 0, 7).
  v5 restarted into `payslips-v5`.
- **Round 4 (2026-11-02, while v5 runs):** branch `fix/round4-rules-schema` (pushed), not released. Group C rest:
  P23 (`6960c31`, rule use case by id + `conflictsWith`), P9 (`7dbcb04`, "Who writes"). v4 leftovers: sub-view fields
  on their screen (`2249b04`; v4 data: fields 84.9 -> 100 percent, citation warnings 3 -> 0). v5 manual step:
  `save_json.py` reads a tool-result file the harness stores for a large answer (`9665a53`, test fixed in
  `661b126`: a grep in the command chain hid one failing test at commit time). Group D: shards keep to one top folder
  (`387e118`). Group E: N1 plugin version in `app-spec.json` (`c8f0b5b`). Tests: 386 Python, 36 Node.
  Left in group E: N2/P3/P24 (single-judge label without the Workflow tool), P20/P22 (runner: needs Dan's Devin
  files), N3 (Devin allow-list doc).
- **v5 assessment (2026-11-02):** full run, both passes, $72.66; render warnings 0 (v4: 40), fields 92.5% (100% with
  Round 4), all in-scope capabilities covered. Exit criteria not met: items 25-28 (Round 5). Manual step: large answers
  stored as files, 3 times (fixed in Round 4, `9665a53`).
- **Round 5 + release 0.6.0 (2026-11-02):** items 25 (`81f3426`, rules findings correct the named cards), 26
  (`efe2692`, endpoints verified through the calling service, inferred ones get a reason), 27 (`4d6d96b`, grader
  resolves bare file names). Item 28 (19 start-page strings) is a person decision: give the reasons in Appendix F
  (`review.py accept`). Released with Round 4 as 0.6.0 (`af14f14`, tag `v0.6.0`), pushed, installed plugin updated.
  Tests: 389 Python, 36 Node. v6 is scheduled to start at 23:55 (after the 5-hour usage window resets at 23:50) into
  `~/Documents/GitHub/vmm3/specs/payslips-v6`.

