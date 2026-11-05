# Builder spec and evidence file: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `render.py spec` writes two files from one render: the builder spec `OUT/NAME` with no code citations, and
the evidence spec `OUT/<stem>.evidence.md` (today's output). The grader gets a `self-contained` check on the builder
spec.

**Architecture:** The renderer keeps producing today's text (the evidence spec). A new pure function
`speclib/builder.py: builder_text(evidence, evidence_name)` derives the builder spec from it line by line. Every
existing grader check, the critic and status read the evidence file; only `self-contained` reads the builder file. The
review loop does not change.

**Tech Stack:** Python 3 standard library (`re`, `unittest`), the existing `speclib` helpers.

**Spec:** `docs/superpowers/specs/2026-10-30-app-spec-design.md` §1 ("plan and build the same feature in a new app
without reading the old code again") and the decision of 2026-11-05 recorded in `docs/HANDOVER.md`: citations are
evidence for reviewers, not content for builders. Plugin folder below: `P/` = `plugins/app-spec`.

## Global Constraints

- The builder file keeps the name the person gives (`--name`, default `SPEC.md`), because `/issues` and people open
  that name. The evidence file is `<stem>.evidence.md` beside it (`payslips.md` -> `payslips.evidence.md`,
  `SPEC.md` -> `SPEC.evidence.md`).
- A citation is `CITE_RE` (from `speclib/template.py`) followed by `:<n>` or `:<n>-<m>`. Endpoint paths such as
  `/v1/payslips/{id}` have no `:<n>` and are never citations.
- `builder_text` is a pure function of its input: no clock, no file reads, no random order.
- Fenced code blocks (```` ``` ````) pass through `builder_text` unchanged and are skipped by every new check.
- The 8 template headings and the 6 appendix headings stay in the builder file, in the same order.
- One fix per commit, each with a test that fails without it. Add a line to `## Unreleased` in `P/CHANGELOG.md` per
  task, in plain words. Commit messages end with the session's co-author trailer.
- Tests: from `P/scripts`, `python3 -m unittest discover -s tests -q`; from `P/`, `node --test tests/workflows.test.mjs`
  and `node --test tests/devin_workflow.test.mjs`. Baseline: 407 Python, 42 Node, all pass.
- Do not edit `plugins/` while an acceptance run is going: the marketplace is a directory source.

## Review Focus

1. **A citation inside a sentence**, such as `(cites \`A.swift:3\` and \`B.swift:9-12\`)`: the sentence must stay
   grammatical, with no `()`, `( , )`, `and .` or doubled spaces left. Pinned in Task 1,
   `test_citation_lists_in_parentheses_leave_no_debris`.
2. **A table whose only cited column is the last one**, and a table where a cell other than `Source`/`Evidence` holds a
   citation (the Data table's `Evidence`, the Authorization header row with a citation in `Source`). Every row must
   keep the same number of cells as its header. Pinned in Task 1, `test_dropping_a_column_keeps_rows_aligned`.
3. **A string key that the builder spec names but Appendix D does not list** (v9: `COMMON_DATA_LOADING_ERROR` in
   AC14). The renderer must add it with its text when the inventory has the text, and the grader must fail when no
   text exists. Pinned in Task 2 and Task 3.
4. **An old output folder** that has only `payslips.md` with citations (v1 to v9). `grade.py` and `status.py` must say
   "run render.py spec" and not grade a stale or missing evidence file. Pinned in Task 3,
   `test_missing_evidence_file_asks_for_render`, and Task 4.
5. **A `--name` that already ends in `.evidence.md`**: it would make the evidence file
   `x.evidence.evidence.md` and confuse the two outputs. `target()` must refuse it. Pinned in Task 2,
   `test_name_ending_in_evidence_md_is_refused`.

---

### Task 1: `builder_text`, the citation stripper

**Files:**
- Create: `P/scripts/speclib/builder.py`
- Test: `P/scripts/tests/test_builder.py`

**Interfaces:**
- Consumes: `CITE_RE`, `APPENDICES` from `speclib/template.py`.
- Produces:
  - `CITATION: re.Pattern` = `CITE_RE + r":\d+(?:-\d+)?"`, compiled.
  - `evidence_name(name: str) -> str`: `"payslips.md"` -> `"payslips.evidence.md"`, `"SPEC.md"` -> `"SPEC.evidence.md"`,
    `"docs/a.md"` -> `"docs/a.evidence.md"`, a name with no `.md` gets `.evidence.md` appended.
  - `builder_text(evidence: str, evidence_name: str) -> str`.
  - `outside_code(text: str) -> Iterator[tuple[int, str]]`: 1-based line number and line, for lines outside fenced code.

Rules of `builder_text`, applied per line outside fenced code, in this order:

1. **Header:** drop the `Module scope:` line and the `- Core:` / `- Touch point:` lines under it, up to the next
   blank line. Keep the title, `Source:` and `Reference HEADs:` lines.
2. **Tables:** find the header row (a `|` row followed by `|---`). Drop every column whose header cell is `Source` or
   `Evidence`, in the header, the `|---|` row and every body row of that table. In a `Design` column, replace
   `carry-as-is (<anything>)` with `carry-as-is`. Split cells on `|` that is not preceded by `\` (the renderer escapes
   `|` in cells as `\|`).
3. **Labelled bullets:** drop a line that matches `^\s*- \*\*(Source|Evidence|Citations?):\*\*` when nothing but
   citations, commas, `and` and spaces is left after rule 4.
4. **Inline citations:** remove every backticked citation (`` `X.swift:12` ``, `` `X.swift:12-30` ``) and every bare
   `CITATION` match. Then clean, repeating until the line stops changing:
   - a parenthesis that holds only spaces, commas, semicolons, `and`, `cites`, `see`, `in`: remove it with its
     leading space;
   - a `Source:`, `Evidence:` or `Cited in:` label followed by only spaces and punctuation up to the end of the
     sentence: remove it;
   - `, ,` -> `,`; ` ,` -> `,`; ` .` -> `.`; ` ;` -> `;`; two or more spaces -> one space; a trailing `,` or `;` before
     `.` is removed.
5. **UNKNOWN notes:** in `UNKNOWN; searched: <text>; owner: <owner>`, remove `searched: <text>; ` and keep
   `UNKNOWN; owner: <owner>`.
6. **Appendix F:** replace the body under `APPENDICES[5]` (up to the next `## ` heading or the end) with one line:
   `` Coverage evidence and every citation: `<evidence_name>`. ``

- [ ] **Step 1: Write the failing tests** in `test_builder.py`, one `unittest.TestCase`, these tests and exact values:

```python
def test_evidence_name(self):
    self.assertEqual(builder.evidence_name("payslips.md"), "payslips.evidence.md")
    self.assertEqual(builder.evidence_name("SPEC.md"), "SPEC.evidence.md")
    self.assertEqual(builder.evidence_name("docs/a.md"), "docs/a.evidence.md")
    self.assertEqual(builder.evidence_name("notes"), "notes.evidence.md")

def test_citation_lists_in_parentheses_leave_no_debris(self):
    line = "The list pages back only (`A/B.swift:3`, `C/D.swift:9-12`). It stops at the end (cites `E.swift:4` and `F.kt:7`)."
    self.assertEqual(builder.builder_text(line + "\n", "x.evidence.md"), "The list pages back only. It stops at the end.\n")

def test_source_label_with_only_a_citation_is_removed(self):
    text = "An employee reads their payslips. Source: `Mod/List.swift:8`\n"
    self.assertEqual(builder.builder_text(text, "x.evidence.md"), "An employee reads their payslips.\n")

def test_source_bullet_is_dropped(self):
    text = "- **Rule:** Shows the card.\n- **Source:** `Employee/StartPage/StartPageViewModel.swift:211-219`\n"
    self.assertEqual(builder.builder_text(text, "x.evidence.md"), "- **Rule:** Shows the card.\n")

def test_dropping_a_column_keeps_rows_aligned(self):
    text = ("| Name | Type | Source |\n|---|---|---|\n"
            "| id | String | `A.swift:3` |\n| note | String a \\| b | `B.swift:4` |\n")
    self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                     "| Name | Type |\n|---|---|\n| id | String |\n| note | String a \\| b |\n")

def test_design_column_loses_its_citation(self):
    text = ("| CAP | Name | Design |\n|---|---|---|\n"
            "| CAP-029 | Browse | carry-as-is (me-ios Mod/Paging.swift:59-124) |\n")
    self.assertIn("| CAP-029 | Browse | carry-as-is |", builder.builder_text(text, "x.evidence.md"))

def test_unknown_keeps_owner_drops_search_note(self):
    text = "- **Client:** UNKNOWN; searched: Reports/, grep exportYearEnd; owner: backend team\n"
    self.assertEqual(builder.builder_text(text, "x.evidence.md"), "- **Client:** UNKNOWN; owner: backend team\n")

def test_endpoint_paths_are_not_citations(self):
    text = "Calls `GET /v1/payslips/{id}` and `GET /v1/reports`.\n"
    self.assertEqual(builder.builder_text(text, "x.evidence.md"), text)

def test_fenced_code_is_unchanged(self):
    text = "```\nsee `A.swift:3`\n```\n"
    self.assertEqual(builder.builder_text(text, "x.evidence.md"), text)

def test_header_drops_module_scope(self):
    text = ("# M spec\n\nSource: module M of me-ios\nReference HEADs: me-ios `abc`\n\n"
            "Module scope:\n- Core: 2 files in `Employee/X`\n- Touch point: `Employee/Y.swift` (uses type Z).\n\n## Summary\n")
    self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                     "# M spec\n\nSource: module M of me-ios\nReference HEADs: me-ios `abc`\n\n## Summary\n")

def test_appendix_f_points_to_the_evidence_file(self):
    text = f"{template.APPENDICES[5]}\n\n| Class | Covered |\n|---|---|\n| screens | 25 |\n"
    self.assertEqual(builder.builder_text(text, "payslips.evidence.md"),
                     f"{template.APPENDICES[5]}\n\nCoverage evidence and every citation: `payslips.evidence.md`.\n")
```

- [ ] **Step 2: Run the tests and see them fail**

Run (from `P/scripts`): `python3 -m unittest tests.test_builder -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'speclib.builder'`.

- [ ] **Step 3: Implement `speclib/builder.py`** with the interface and the six rules above. Process the text as a
  list of lines with a small state machine (in code fence, in table with dropped column indexes, in Appendix F).

- [ ] **Step 4: Run the tests and see them pass**

Run: `python3 -m unittest tests.test_builder -v` — Expected: 11 tests, OK.

- [ ] **Step 5: Check it on real output.** Run `builder_text` on
  `~/Documents/GitHub/vmm3/specs/payslips-v9/payslips.md` (read-only; write the result to the session scratchpad) and
  count what `CITATION` still matches outside code. Expected: 0. Read 40 random changed lines for debris
  (`()`, `( ,`, `  `, ` .`). Each new debris shape becomes a test in Step 1 before you fix it.

- [ ] **Step 6: Commit** `feat(builder): derive a citation-free builder spec from the evidence spec`, with a
  CHANGELOG line.

---

### Task 2: `render.py spec` writes both files, and Appendix D lists every key the spec names

**Files:**
- Modify: `P/scripts/speclib/spec_md.py` (`target`, `write`, `strings_and_platform`)
- Modify: `P/scripts/render.py` (`spec`, `main`: print both paths)
- Test: `P/scripts/tests/test_render_spec.py`

**Interfaces:**
- Consumes: `builder.evidence_name`, `builder.builder_text` (Task 1).
- Produces: `spec_md.write(dest, name="SPEC.md") -> str` writes `evidence_name(name)` with the full text and `name`
  with `builder_text(...)`; returns the builder text. `render.py spec OUT --name N` prints two lines, `OUT/N` then
  `OUT/<evidence name>`.

- [ ] **Step 1: Write the failing tests** in `test_render_spec.py`:
  - `test_spec_writes_builder_and_evidence_files`: after `render.spec(dest, "payslips.md")`, both
    `payslips.md` and `payslips.evidence.md` exist; the evidence file contains `` `Modules/PayslipsFeature/PayslipListView.swift:8` ``
    (from the fixture prose), and `builder.CITATION.search` finds nothing in the builder file outside code.
  - `test_name_ending_in_evidence_md_is_refused`: `render.spec(dest, "x.evidence.md")` exits with code 2 and a message
    that names `--name`.
  - `test_appendix_d_lists_every_string_key_the_spec_names`: give a prose criterion the text
    `"Shows COMMON_DATA_LOADING_ERROR."`, put `"COMMON_DATA_LOADING_ERROR": "Please check your internet connection or try again later."`
    into the fixture inventory `strings.allValues`; the Strings table in Appendix D then has the row
    `| COMMON_DATA_LOADING_ERROR | Please check your internet connection or try again later. |`.
- [ ] **Step 2: Run them and see them fail.** `python3 -m unittest tests.test_render_spec -v` — the three new tests FAIL.
- [ ] **Step 3: Implement.** In `target()`, refuse a name whose lower-case form ends in `.evidence.md`. In `write()`,
  render once, save the evidence file, then the builder file. In `strings_and_platform`, add a row for every
  inventory key (`strings.keys` ∪ `strings.allValues`) that appears as a whole word in the rendered sections 1 to 8
  and in Appendices A to C, with its text from `strings.values`, else `strings.allValues`. Keys with no text get no row
  (Task 3 reports them). Keep the table sorted by key, as today.
- [ ] **Step 4: Run the whole Python suite.** Expected: all pass. A test that read `SPEC.md` for a citation now reads
  `SPEC.evidence.md`: change only the file it reads, never its assertion.
- [ ] **Step 5: Commit** `feat(render): write the builder spec and the evidence spec`, with a CHANGELOG line.

---

### Task 3: grader reads the evidence file, and the `self-contained` check

**Files:**
- Modify: `P/scripts/grade.py` (`CHECKS`, `_Grader.__init__`, new `self_contained`)
- Test: `P/scripts/tests/test_grade.py`

**Interfaces:**
- Consumes: `builder.evidence_name`, `builder.CITATION`, `builder.outside_code` (Task 1); both files from Task 2.
- Produces: `CHECKS` gets `"self-contained"` as the last entry. `_Grader` loads `self.spec` from the evidence file and
  `self.builder` (raw text) from `name`.

`self_contained()` returns a list of items, one per problem, in this order:

1. `leftover citation <token> (line <n>)` for each `CITATION` match in the builder file outside code.
2. `string key <KEY> has no text (line <n>)` for each inventory key (`strings.keys` ∪ `strings.allValues` ∪ every
   whole word that matches `[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+` inside backticks) that the builder names outside the
   Appendix D Strings table and that has no row with non-empty text in that table.
3. `points to the code (line <n>): <phrase>` for each match, case-insensitive, of
   `\bsee (?:the )?(?:code|source|file|implementation)\b`, `\bin the cited (?:code|files?|lines?)\b`,
   `\bas (?:the )?(?:code|source) (?:shows|does|says)\b`.

- [ ] **Step 1: Write the failing tests:**
  - `test_good_fixture_is_self_contained`: `make_good` then `grade.run(dest)`; the `self-contained` check passes.
  - `test_leftover_citation_fails`: write a builder file by hand that contains `` `A.swift:3` ``; the check fails
    with detail containing `leftover citation`.
  - `test_string_key_without_text_fails`: a criterion naming `SERVER_ERROR_TEXT` with no text anywhere; detail
    contains `string key SERVER_ERROR_TEXT has no text`.
  - `test_pointer_to_code_fails`: a criterion with text `"Rounding is as the code does it."`; detail contains
    `points to the code`.
  - `test_missing_evidence_file_asks_for_render`: delete `SPEC.evidence.md`; `grade.run` exits 2 with a message that
    names `render.py spec`.
- [ ] **Step 2: Run them and see them fail.** `python3 -m unittest tests.test_grade -v`.
- [ ] **Step 3: Implement** as specified. The missing-file message: `"<path> not found (run render.py spec first)"`,
  as for the builder file today.
- [ ] **Step 4: Run the whole Python suite.** Expected: all pass. An existing grade test that edits `SPEC.md` by hand
  to break a check now edits `SPEC.evidence.md`: change only the file it edits, never its assertion.
- [ ] **Step 5: Commit** `feat(grade): check that the builder spec stands without the code`, with a CHANGELOG line.

---

### Task 4: status reads the evidence file

**Files:**
- Modify: `P/scripts/status.py` (`_coverage_differs`, `_stale`)
- Test: `P/scripts/tests/test_status.py`

**Interfaces:**
- Consumes: `builder.evidence_name`.
- Produces: `_coverage_differs` reads Appendix F from the evidence file. `_stale` compares times with the older of the
  two spec files, and reports `the spec predates the evidence split: re-run render.py spec` when the builder file
  exists and the evidence file does not.

- [ ] **Step 1: Write the failing tests:** `test_old_folder_without_evidence_asks_for_render` (only `SPEC.md` exists:
  the stale list contains that line) and `test_coverage_read_from_evidence_file` (after render, editing the builder
  file's Appendix F does not make status report the spec as stale; editing the evidence file's Appendix F does).
- [ ] **Step 2: Run them and see them fail.** `python3 -m unittest tests.test_status -v`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the whole Python suite.** Expected: all pass.
- [ ] **Step 5: Commit** `fix(status): read coverage and times from the evidence spec`, with a CHANGELOG line.

---

### Task 5: skills, critic and docs name the two files

**Files:**
- Modify: `P/skills/spec/SKILL.md` (front-matter description, step 7.2, step 8 note, the Finish section near line 375)
- Modify: `P/skills/review/SKILL.md`, `P/agents/spec-critic.md` (item 2 of what to read, plus one rule),
  `P/agents/spec-writer.md` (one rule), `P/docs/DESIGN.md` (outputs), `P/README.md` (outputs)
- Test: `P/scripts/tests/test_docs.py`

Exact text to add:
- spec-critic, item 2: "The evidence spec, `<out>/<stem>.evidence.md`. The builder spec `<out>/<name>` is the same text
  with every citation removed; builders read only that file."
- spec-critic, new rule under the severity list: "A requirement that is complete only through its citation (a string
  key without its text, a value or a limit only in the cited code, 'see the code') is **High**, owner `writer`, or
  `rules` for a rule card."
- spec-writer, new rule: "Write every value, text, limit and error reaction into the sentence. The builder spec drops
  all citations, so a sentence that needs its citation to be complete is a defect."
- spec/SKILL.md step 7.2: the critic gets the evidence file's name. Finish: "Builders read `OUT/NAME`. Reviewers and
  `compare` read `OUT/<stem>.evidence.md`."

- [ ] **Step 1: Write the failing test** `test_skill_and_critic_name_the_evidence_file` in `test_docs.py`: the
  strings `.evidence.md` appear in `skills/spec/SKILL.md`, `skills/review/SKILL.md` and `agents/spec-critic.md`, and
  `complete only through its citation` appears in `agents/spec-critic.md`.
- [ ] **Step 2: Run it and see it fail.**
- [ ] **Step 3: Make the text changes above.**
- [ ] **Step 4: Run both test suites** (Python, and the two Node files). Expected: all pass.
- [ ] **Step 5: Commit** `docs: name the builder spec and the evidence spec`, with a CHANGELOG line.

---

### Task 6: release and check on v9

- [ ] **Step 1:** Copy `~/Documents/GitHub/vmm3/specs/payslips-v9` to `~/Documents/GitHub/vmm3/specs/payslips-v9-split`.
  Run `render.py spec <copy> --name payslips.md` and `grade.py <copy> --name payslips.md` from the repo's
  `P/scripts`. Record: builder line count, citations left (expected 0), and every `self-contained` item. Expected
  items include `COMMON_DATA_LOADING_ERROR` and `SERVER_ERROR_TEXT` unless the inventory has their text.
- [ ] **Step 2:** Release 0.10.0 as in `docs/HANDOVER.md` step 4 (merge, bump `plugin.json` and `marketplace.json`,
  CHANGELOG heading, `release: app-spec 0.10.0`, tag `v0.10.0`), then push `main` and the tag.
- [ ] **Step 3:** Add a Round log entry to `docs/HANDOVER.md` with the Step 1 numbers. Next run: `payslips-v10`.
