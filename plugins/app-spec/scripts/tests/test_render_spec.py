import os
import re
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out, template
from test_render_catalogs import build_out, read_text, write_overrides

import render

ALIAS_INDEX = FIX / "results" / "capability_index_alias.json"


def section(text, heading):
    """The lines of the section that starts at `heading`, up to the next `## ` heading."""
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def prose():
    """A small synthetic prose.json for the ios fixture (UC-001 and UC-002 have criteria, UC-003 does not)."""
    return {
        "summary": "An employee reads their payslips. Source: Modules/PayslipsFeature/PayslipListView.swift:8",
        "screens": {"SCR-001": {"purpose": "List the payslips of the year.",
                                "states": [{"name": "empty", "shows": "No payslips yet",
                                            "evidence": "Modules/PayslipsFeature/PayslipListView.swift:20"}]}},
        "keepDrop": {"UC-001": {"keep": ["newest first"], "drop": [{"what": "list view model", "file": "A.swift:3"}]}},
        "data": [{"entity": "Payslip", "fields": "id, date", "storage": "none", "lifetime": "session",
                  "evidence": "PayslipItem.swift:3"}],
        "dependencies": ["The Employee API stays as it is. Source: GetPayslips.swift:6"],
        "openQuestions": [{"id": "Q-1", "question": "Is gross shown to part-timers?", "searched": "PayslipItem.swift",
                           "owner": "payroll"}],
        "criteria": [
            {"ids": ["UC-001"], "text": "The newest payslip is on top.", "evidence": "PayslipItem.swift:10-20"},
            {"ids": ["UC-001", "UC-002"], "text": "Tapping a row opens its details.", "evidence": "PayslipListView.swift:14"},
        ],
    }


class TestSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")
        render.catalogs(self.out)

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def with_prose(self):
        out.save(self.out, "prose.json", prose())

    # ------------------------------------------------------------ the brief

    def test_spec_has_template_headings_in_order(self):
        text = render.spec(self.out)
        heads = [l for l in text.splitlines() if l.startswith("## ")]
        self.assertEqual(heads[:8], template.HEADINGS)
        self.assertEqual(heads[8:], template.APPENDICES)

    def test_spec_header_lines(self):
        text = render.spec(self.out)
        self.assertIn("Source: module Payslips of ios-app (no source issue)", text)
        self.assertRegex(text, r"Reference HEADs: ios-app `[0-9a-f]{7,}`")

    def test_criteria_numbering_is_contiguous(self):
        for with_prose in (False, True):
            if with_prose:
                self.with_prose()
            nums = [int(m.group(1)) for m in re.finditer(template.AC_RE, render.spec(self.out), re.M)]
            self.assertEqual(nums, list(range(1, len(nums) + 1)))
            self.assertGreater(len(nums), 0)

    def test_design_column_is_carry_as_is(self):
        self.assertRegex(render.spec(self.out), r"\| UC-001 \| [^|]+ \| carry-as-is \(ios-app [^)]+:\d+\) \|")

    def test_dropped_field_leaves_appendix_a_and_enters_f(self):
        before = section(render.spec(self.out), "## Appendix A. Fields and ids")
        self.assertIn("pay.list.title", before)
        write_overrides(self.out, {"drop": [{"kind": "field", "id": "SCR-001.title", "reason": "not user-facing"}]})
        text = render.spec(self.out)
        a, f = section(text, "## Appendix A. Fields and ids"), section(text, "## Appendix F. Coverage")
        self.assertNotIn("SCR-001.title", a)
        self.assertNotIn("pay.list.title", a)  # the row is gone, not only the id
        self.assertIn("SCR-001.title", f)
        self.assertIn("not user-facing", f)

    # ------------------------------------------------------------ more

    def test_template_constants(self):
        self.assertEqual(template.HEADINGS[0], "## Summary")
        self.assertEqual(len(template.HEADINGS), 8)
        self.assertEqual(len(template.APPENDICES), 6)
        self.assertEqual(template.APPENDICES[-1], "## Appendix F. Coverage")
        self.assertTrue(re.match(template.AC_RE, "- **AC1 (UC-001, CAP-012):** text"))
        self.assertFalse(re.match(template.AC_RE, "- **AC1 (UC-01):** text"))

    def test_spec_is_deterministic_and_written_inside_out(self):
        self.with_prose()
        text = render.spec(self.out)
        first = read_text(self.out, "SPEC.md")
        self.assertEqual(first, text)
        render.spec(self.out)
        self.assertEqual(read_text(self.out, "SPEC.md"), first)

    def test_name_is_a_file_inside_out_and_nothing_escapes(self):
        render.spec(self.out, "docs/specs/payslips.md")
        self.assertTrue(os.path.isfile(os.path.join(self.out, "docs", "specs", "payslips.md")))
        for bad in ("../escape.md", "/tmp/escape.md", "a/../../escape.md"):
            code, _, err = run_cli(["render.py", "spec", self.out, "--name", bad], module=render)
            self.assertEqual(code, 2, bad)
            self.assertIn("inside", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.md")))

    def test_cli_runs_spec(self):
        code, stdout, err = run_cli(["render.py", "spec", self.out, "--name", "X.md"], module=render)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "X.md")))
        self.assertIn("X.md", stdout)

    def test_missing_catalogs_exit_2(self):
        os.remove(os.path.join(self.out, "use-cases.json"))
        code, _, err = run_cli(["render.py", "spec", self.out], module=render)
        self.assertEqual(code, 2)
        self.assertIn("use-cases.json", err)

    def test_without_prose_every_slot_is_unknown_and_criteria_are_placeholders(self):
        text = render.spec(self.out)
        self.assertIn("UNKNOWN — summary not written yet", section(text, "## Summary"))
        self.assertIn("UNKNOWN", section(text, "## Appendix B. Data"))
        criteria = re.findall(template.AC_RE, text, re.M)
        n_cases = len(out.load(self.out, "use-cases.json")["useCases"])
        self.assertEqual(len(criteria), n_cases)
        for uc in ("UC-001", "UC-002", "UC-003"):
            self.assertRegex(text, rf"- \*\*AC\d+ \({uc}\):\*\* UNKNOWN — criterion not written yet")

    def test_prose_fills_the_slots(self):
        self.with_prose()
        text = render.spec(self.out)
        self.assertIn("An employee reads their payslips.", section(text, "## Summary"))
        self.assertIn("List the payslips of the year.", section(text, "## Screens"))
        self.assertIn("The newest payslip is on top.", section(text, "## Acceptance criteria"))
        self.assertIn("- **AC2 (UC-001, UC-002):** Tapping a row opens its details.", text)
        self.assertIn("Is gross shown to part-timers?", section(text, "## Open questions"))
        self.assertIn("The Employee API stays as it is.", section(text, "## Dependencies and decisions"))
        self.assertIn("Payslip", section(text, "## Appendix B. Data"))
        self.assertIn("newest first", section(text, "## Appendix C. Behaviour to keep, implementation to drop"))

    def test_a_use_case_without_a_written_criterion_gets_a_placeholder_after_the_prose_ones(self):
        self.with_prose()
        text = render.spec(self.out)
        lines = [l for l in section(text, "## Acceptance criteria").splitlines() if l.startswith("- **AC")]
        self.assertEqual(len(lines), 3)  # two written (covering UC-001 and UC-002), then UC-003's placeholder
        self.assertTrue(any("UC-003" in l and "UNKNOWN" in l for l in lines))
        self.assertFalse(any("(UC-002):" in l and "UNKNOWN" in l for l in lines))

    def test_a_criterion_without_a_use_case_id_is_not_numbered(self):
        data = prose()
        data["criteria"].append({"ids": [], "text": "Orphan statement.", "evidence": "x.swift:1"})
        out.save(self.out, "prose.json", data)
        text = render.spec(self.out)
        self.assertIn("UNKNOWN — criterion without a use case id: Orphan statement.", text)
        nums = [int(m.group(1)) for m in re.finditer(template.AC_RE, text, re.M)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))

    def test_alias_is_shown_instead_of_the_uc_id(self):
        render_out = build_out(self.tmp, "aliased", index=ALIAS_INDEX)
        render.catalogs(render_out)
        cases = out.load(render_out, "use-cases.json")["useCases"]
        aliased = next(u for u in cases if u["alias"])
        text = render.spec(render_out)
        caps = section(text, "## Capabilities")
        self.assertIn(f"| {aliased['alias']} |", caps)
        self.assertNotIn(f"| {aliased['id']} |", caps)
        crit = section(text, "## Acceptance criteria")
        self.assertIn(f"({aliased['alias']})", crit)
        self.assertNotIn(aliased["id"], crit)
        self.assertEqual(len(re.findall(template.AC_RE, text, re.M)), len(cases))

    def test_prose_criterion_with_a_uc_id_is_shown_with_its_alias(self):
        render_out = build_out(self.tmp, "aliased2", index=ALIAS_INDEX)
        render.catalogs(render_out)
        aliased = next(u for u in out.load(render_out, "use-cases.json")["useCases"] if u["alias"])
        out.save(render_out, "prose.json", {"criteria": [{"ids": [aliased["id"]], "text": "Works.", "evidence": "a.swift:1"}]})
        crit = section(render.spec(render_out), "## Acceptance criteria")
        self.assertIn(f"- **AC1 ({aliased['alias']}):** Works.", crit)

    def test_rules_are_ordered_by_priority_then_id(self):
        data = out.load(self.out, "rules.json")
        base = data["rules"][0]
        data["rules"] = [
            {**base, "id": "RULE-001", "name": "Low one", "priority": "P2"},
            {**base, "id": "RULE-002", "name": "Top one", "priority": "P0", "confidence": "Low", "question": "Why zero?"},
            {**base, "id": "RULE-003", "name": "Mid one", "priority": "P1"},
            {**base, "id": "RULE-004", "name": "Mid two", "priority": "P1"},
        ]
        out.save(self.out, "rules.json", data)
        rules = section(render.spec(self.out), "## Business rules and permissions")
        order = [rules.index(n) for n in ("Top one", "Mid one", "Mid two", "Low one")]
        self.assertEqual(order, sorted(order))
        self.assertIn("Given", rules)
        self.assertIn("Why zero?", rules)  # low confidence carries its question
        self.assertEqual(rules.count("Question:"), 1)  # High confidence carries none

    def test_rule_shows_gwt_parameters_source_and_confidence(self):
        rules = section(render.spec(self.out), "## Business rules and permissions")
        self.assertIn("RULE-001", rules)
        self.assertIn("three payslips", rules)
        self.assertIn("PayslipItem.swift:10-20", rules)
        self.assertIn("High", rules)

    def test_endpoint_section_shows_fields_errors_label_clients_and_backend(self):
        data = out.load(self.out, "endpoints.json")
        e = next(x for x in data["endpoints"] if x["path"].endswith("/payslips"))
        e["auth"] = "bearer token"
        e["request"]["fields"] = [{"name": "year", "type": "int", "required": False, "nullable": "no"}]
        e["response"]["fields"] = [{"name": "gross", "type": "decimal", "required": False, "nullable": "explicit"}]
        e["errors"] = [{"status": 404, "reaction": "shows the not-found state"}]
        e["backend"] = {"repo": "me-api", "file": "Controllers/PayslipController.cs", "line": 40, "auth": "policy Employee"}
        e["disagreements"] = [{"field": "gross", "client": "GetPayslips.swift:9", "backend": "Payslip.cs:12",
                               "note": "backend names it grossPay"}]
        out.save(self.out, "endpoints.json", data)
        text = render.spec(self.out)
        eps = section(text, "## Endpoints")
        self.assertIn(f"{e['id']} — GET {e['path']}", eps)
        for needle in ("bearer token", "year", "decimal", "explicit", "404", "shows the not-found state", "VERIFIED",
                       "GetPayslips.swift", "me-api", "Controllers/PayslipController.cs:40", "policy Employee"):
            self.assertIn(needle, eps)
        # the disagreement sits under its own endpoint, before the next endpoint heading
        block = eps.split("### ")[next(i for i, b in enumerate(eps.split("### ")) if e["id"] in b)]
        self.assertIn("backend names it grossPay", block)
        self.assertIn("GetPayslips.swift:9", block)
        self.assertIn("Payslip.cs:12", block)

    def test_appendix_a_lists_identifier_or_proposed_id(self):
        a = section(render.spec(self.out), "## Appendix A. Fields and ids")
        self.assertIn("pay.list.title", a)  # the existing identifier
        self.assertIn("payslips.paysliplistview.refresh", a)  # a proposal

    def test_appendix_f_without_ledger_and_with_ledger(self):
        f = section(render.spec(self.out), "## Appendix F. Coverage")
        self.assertIn("Coverage not computed yet: run ledger.py", f)
        out.save(self.out, "ledger.json", {"version": 1, "pass": False,
                                           "classes": {"screens": {"total": 4, "covered": 3,
                                                                   "uncovered": [{"item": "DebugScreen", "reason": None}]}},
                                           "thresholds": {"screens": 100}})
        f = section(render.spec(self.out), "## Appendix F. Coverage")
        self.assertNotIn("not computed", f)
        self.assertIn("DebugScreen", f)
        self.assertIn("| screens | 3 | 4 | 100 |", f)

    def test_dropped_screen_and_endpoint_and_use_case_leave_their_sections(self):
        write_overrides(self.out, {"drop": [{"kind": "screen", "id": "SCR-002", "reason": "dead code"},
                                            {"kind": "useCase", "id": "UC-003", "reason": "out of module"}]})
        text = render.spec(self.out)
        self.assertNotIn("PayslipDetailView (SCR-002)", section(text, "## Screens"))
        self.assertNotIn("| UC-003 |", section(text, "## Capabilities"))
        self.assertNotIn("(UC-003)", section(text, "## Acceptance criteria"))
        f = section(text, "## Appendix F. Coverage")
        self.assertIn("SCR-002", f)
        self.assertIn("dead code", f)
        self.assertIn("UC-003", f)

    def test_flows_render_with_steps_in_appendix_e(self):
        e = section(render.spec(self.out), "## Appendix E. Flows")
        self.assertIn("FLOW-001", e)
        self.assertIn("tap the first row", e)

    def test_spec_never_writes_the_other_files(self):
        write_overrides(self.out, {"rename": [{"id": "UC-001", "name": "X"}]})
        names = ("overrides.json", "app-spec.json", "ids.json", "use-cases.json")
        before = [read_text(self.out, n) for n in names]
        render.spec(self.out)
        self.assertEqual(before, [read_text(self.out, n) for n in names])

    def test_contract_repos_follow_the_app_in_the_reference_heads(self):
        cfg = out.load_config(self.out)
        cfg["contracts"] = [{"path": "/x/me-api", "name": "me-api", "commit": "abcdef1234567"}]
        out.save(self.out, "app-spec.json", cfg)
        self.assertRegex(render.spec(self.out), r"Reference HEADs: ios-app `[0-9a-f]{7,}`, me-api `abcdef1234567`")


if __name__ == "__main__":
    unittest.main()
