"""Structural UNKNOWNs point at open questions, and accepted ledger items are known overrides."""

import re
import shutil
import tempfile
import unittest

from helpers import run_cli
from speclib import out
from test_grade import DETAIL, GETTER, check, edit, make_good
from test_render_catalogs import read_text

import grade
import ledger
import render
import review


def section(text, heading):
    return text.split(heading + "\n", 1)[1].split("\n## ", 1)[0]


class TestStructuralUnknowns(unittest.TestCase):
    """An UNKNOWN endpoint with no auth, errors, response or backend, and a Medium rule with a question."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dest = make_good(cls.tmp, "open")

        def endpoints(data):
            data["endpoints"][0].update(label="UNKNOWN", auth=None, errors=[], response={"fields": []}, backend=None)

        def rules(data):
            data["rules"][1].update(confidence="Medium", question="Why zero?")

        edit(cls.dest, "endpoints.json", endpoints)
        edit(cls.dest, "rules.json", rules)
        render.spec(cls.dest)
        cls.text = read_text(cls.dest, "SPEC.evidence.md")
        cls.ep = out.load(cls.dest, "endpoints.json")["endpoints"][0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_the_spec_passes_the_grade(self):
        result = grade.run(self.dest)
        self.assertEqual([c for c in result["checks"] if not c["pass"]], [])

    def test_structural_unknowns_name_an_open_question(self):
        body = section(self.text, "## Endpoints")
        self.assertNotIn("UNKNOWN — ", body)
        self.assertRegex(body, rf"### {self.ep['id']} — .*\(UNKNOWN \(open question OQ-\d{{3}}\)\)")
        self.assertRegex(body, r"- \*\*Auth:\*\* UNKNOWN \(open question OQ-\d{3}\)")
        self.assertRegex(body, r"- \*\*Errors and UI reaction:\*\* UNKNOWN \(open question OQ-\d{3}\)")
        rules = section(self.text, "## Business rules and permissions")
        self.assertRegex(rules, r"- \*\*Question:\*\* Why zero\? \(open question OQ-\d{3}\)")

    def test_open_questions_list_each_id_with_searched_and_owner(self):
        oq = section(self.text, "## Open questions")
        referenced = set(re.findall(r"open question (OQ-\d{3})", self.text))
        listed = re.findall(r"^- \*\*(OQ-\d{3}):\*\*", oq, re.M)
        self.assertEqual(referenced, set(listed))
        self.assertEqual(len(listed), len(set(listed)))
        for line in oq.splitlines():
            if line.startswith("- **OQ-"):
                self.assertIn("Searched:", line)
                self.assertIn("Owner: owner of ios-app", line)
        rule_line = next(l for l in oq.splitlines() if "Why zero?" in l)
        self.assertIn(f"`{DETAIL}:9`", rule_line)
        self.assertNotIn("UNKNOWN — ", oq)

    def test_open_questions_file_uses_the_same_ids(self):
        review.questions(self.dest)
        md = read_text(self.dest, "OPEN_QUESTIONS.md")
        oq = section(self.text, "## Open questions")
        listed = re.findall(r"^- \*\*((?:OQ|Q)-[\w-]+):\*\*", oq, re.M)
        rows = re.findall(r"^\| ((?:OQ|Q)-[\w-]+) \|", md, re.M)
        self.assertEqual(listed, rows)

    def test_an_unknown_without_a_listed_question_still_fails(self):
        text = self.text.replace("- **Auth:** UNKNOWN (open question OQ-", "- **Auth:** UNKNOWN (open question OQ-9", 1)
        out.save_text(self.dest, "BAD.evidence.md", text)
        out.save_text(self.dest, "BAD.md", read_text(self.dest, "SPEC.md"))  # the builder file the grader also reads
        self.assertFalse(check(grade.run(self.dest, "BAD.md"), "unknowns-have-owner")["pass"])

    def test_prose_placeholder_still_fails(self):
        text = self.text.replace("## Summary\n\n", "## Summary\n\nUNKNOWN — summary not written yet\n\n", 1)
        out.save_text(self.dest, "BAD2.evidence.md", text)
        out.save_text(self.dest, "BAD2.md", read_text(self.dest, "SPEC.md"))  # the builder file the grader also reads
        self.assertFalse(check(grade.run(self.dest, "BAD2.md"), "prose-complete")["pass"])


class TestEveryCatalogGap(unittest.TestCase):
    """Complete prose, and every kind of gap a catalog can have: each UNKNOWN names a listed open question."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dest = make_good(cls.tmp, "gaps")

        def cases(data):
            data["useCases"][0]["evidence"] = "UNKNOWN"
            data["useCases"][1].update(files=["Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipDetailView.swift"],
                                       screens=[])  # a file without a line, and no screen declaration to fall back on
            data["useCases"][2].update(files=[], screens=[])

        def screens(data):
            data["screens"][0].update(actions=[], file=None)

        def endpoints(data):
            data["endpoints"][0].update(label=None, auth=None, errors=[{"status": 500}], backend=None,
                                        response={"fields": [{"name": "id"}]})

        def rules(data):
            data["rules"][0].update(priority=None, category=None, plainEnglish=None, source=None)
            data["rules"][1].update(confidence="Low", question=None)

        edit(cls.dest, "use-cases.json", cases)
        edit(cls.dest, "screens.json", screens)
        edit(cls.dest, "endpoints.json", endpoints)
        edit(cls.dest, "rules.json", rules)
        prose = out.load(cls.dest, "prose.json")
        prose["screens"]["SCR-002"].pop("states")  # the catalog's states show, one with UNKNOWN evidence
        out.save(cls.dest, "prose.json", prose)
        edit(cls.dest, "screens.json", lambda d: d["screens"][1].update(
            states=[{"name": "error", "shows": "A retry button", "evidence": "UNKNOWN"}]))
        render.spec(cls.dest)
        cls.text = read_text(cls.dest, "SPEC.evidence.md")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_unknowns_have_owner_passes(self):
        c = check(grade.run(self.dest), "unknowns-have-owner")
        self.assertTrue(c["pass"], c["detail"])

    def test_every_unknown_in_the_body_names_a_listed_open_question(self):
        body = self.text.split("## Appendix A.", 1)[0]
        listed = set(re.findall(r"^- \*\*(OQ-\d{3}):\*\*", section(self.text, "## Open questions"), re.M))
        for line in body.splitlines():
            if ("UNKNOWN" in line and "UNKNOWN — " not in line  # the writer's placeholders are prose-complete's job
                    and not line.startswith("- **OQ-") and not line.startswith("Evidence labels")):
                refs = set(re.findall(r"open question (OQ-\d{3})", line))
                self.assertTrue(refs and refs <= listed, line)

    def test_a_missing_line_is_not_an_unknown_fact(self):
        caps = section(self.text, "## Capabilities")
        self.assertIn("line not resolved", caps)

    def test_catalog_gaps_leave_no_placeholder_for_the_grader(self):
        c = check(grade.run(self.dest), "prose-complete")
        self.assertTrue(c["pass"], c["detail"])


class TestAcceptedLedgerItems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dest = make_good(self.tmp, "accept")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def test_accepting_every_uncovered_item_passes_overrides_reflected(self):
        module = out.load(self.dest, "module.json")  # the start-page card counts only as a core file
        module["core"].append("Employee/StartPage/PayslipCard.swift")
        out.save(self.dest, "module.json", module)
        ledger.compute(self.dest)
        items = review.uncovered(self.dest)
        kinds = {i["kind"] for i in items}
        self.assertIn("screen", kinds)  # the fixture has a screen no catalog entry covers
        for i in items:
            code, _, err = run_cli(["review.py", "accept", self.dest, "--kind", i["kind"], "--id", i["id"],
                                    "--reason", "out of module"])
            self.assertEqual(code, 0, err)
        led = ledger.compute(self.dest)
        render.spec(self.dest)
        c = check(grade.run(self.dest), "overrides-reflected")
        self.assertTrue(c["pass"], c["detail"])
        self.assertTrue(all(cls["pass"] for name, cls in led["classes"].items() if name in ("screens", "endpoints")))


if __name__ == "__main__":
    unittest.main()
