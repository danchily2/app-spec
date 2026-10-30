import json
import os
import shutil
import tempfile
import unittest

from helpers import run_cli
from speclib import out
from test_render_catalogs import build_out, read_text

import review


class TestReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")
        code, _, err = run_cli(["render.py", "catalogs", self.out])
        self.assertEqual(code, 0, err)

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def critic(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_append_adds_passes_and_writes_the_scorecard(self):
        out.save(self.out, "ledger.json", {"version": 1, "pass": False, "thresholds": {"screens": 100},
                                           "classes": {"screens": {"percent": 50, "pass": False, "uncovered": []}}})
        out.save(self.out, "grade.json", {"version": 1, "pass": True, "checks": [{"name": "sections", "pass": True,
                                                                                    "detail": ""}]})
        first = self.critic("c1.json", [
            {"severity": "High", "section": "Screens", "finding": "SCR-001 has no error state", "fix": "add it",
             "owner": "writer"},
            {"severity": "Nit", "section": "Summary", "finding": "long", "fix": "shorten", "owner": "writer"},
            {"severity": "Critical", "section": "x", "finding": "bad severity", "fix": "", "owner": "writer"},
            {"severity": "High", "section": "x", "finding": "bad owner", "fix": "", "owner": "spec-writer"}])
        code, stdout, err = run_cli(["review.py", "append", self.out, "--critic", first])
        self.assertEqual(code, 0, err)
        self.assertIn("2 finding(s) left out", err)
        second = self.critic("c2.json", {"findings": [{"severity": "Medium", "section": "Endpoints", "finding": "f",
                                                        "fix": "x", "owner": "contracts"}]})
        run_cli(["review.py", "append", self.out, "--critic", second])
        doc = out.load(self.out, "review.json")
        self.assertEqual([p["n"] for p in doc["passes"]], [1, 2])
        self.assertEqual(doc["passes"][0], {"n": 1, "ledger": {"pass": False}, "grade": {"pass": True},
                                            "critic": [{"severity": "High", "section": "Screens",
                                                        "finding": "SCR-001 has no error state", "fix": "add it",
                                                        "owner": "writer"},
                                                       {"severity": "Nit", "section": "Summary", "finding": "long",
                                                        "fix": "shorten", "owner": "writer"}]})
        md = read_text(self.out, "REVIEW.md")
        self.assertIn("| 1 | fail | pass | 0 | 1 | 0 | 1 |", md)
        self.assertIn("## Findings that remain after pass 2", md)
        self.assertIn("**Medium, Endpoints** (owner: contracts)", md)
        self.assertNotIn("SCR-001 has no error state", md.split("## Findings that remain")[1])
        self.assertIn("- Ledger, screens: 50 percent of 100 percent", md)

    def test_reset_removes_both_files(self):
        run_cli(["review.py", "append", self.out, "--critic", self.critic("c.json", [])])
        self.assertTrue(os.path.isfile(os.path.join(self.out, "REVIEW.md")))
        code, _, _ = run_cli(["review.py", "reset", self.out])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.out, "review.json")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "REVIEW.md")))

    def test_questions_take_prose_rules_and_unknown_endpoints(self):
        out.save(self.out, "prose.json", {"openQuestions": [{"id": "Q-1", "question": "Is gross shown?",
                                                             "searched": "`A.swift:3`", "owner": "payroll team"}]})
        rules = out.load(self.out, "rules.json")
        rules["rules"][0].update(question="Is the limit 3 or 4?", confidence="Medium")
        rules["rules"][1].update(question="Asked of a High rule", confidence="High")  # High rules ask nothing
        out.save(self.out, "rules.json", rules)
        eps = out.load(self.out, "endpoints.json")
        eps["endpoints"][0]["label"] = "UNKNOWN"
        eps["endpoints"][0]["reason"] = "the response type is generated"
        out.save(self.out, "endpoints.json", eps)
        code, stdout, err = run_cli(["review.py", "questions", self.out])
        self.assertEqual(code, 0, err)
        md = read_text(self.out, "OPEN_QUESTIONS.md")
        self.assertIn("| Q-1 | Is gross shown? | `A.swift:3` | payroll team |", md)
        self.assertRegex(md, rf"\| OQ-\d{{3}} \| Is the limit 3 or 4\? \({rules['rules'][0]['id']}\) \| "
                             rf"`{rules['rules'][0]['source']}` \| owner of ios-app \|")
        self.assertNotIn("Asked of a High rule", md)
        self.assertRegex(md, rf"\| OQ-\d{{3}} \| What are the contract \(the response type is generated\).*"
                             rf"\({eps['endpoints'][0]['id']}\)\?")

    def test_uncovered_and_accept(self):
        eps = out.load(self.out, "endpoints.json")["endpoints"]
        ep = eps[0]
        out.save(self.out, "ledger.json", {"version": 1, "pass": False, "classes": {
            "endpoints": {"uncovered": [{"item": f"{ep['method']} {ep['path']}", "reason": None},
                                        {"item": "GET /other", "reason": None}]},
            "strings": {"uncovered": [{"item": "pay.title", "reason": "not user-facing"}]}}})
        code, stdout, _ = run_cli(["review.py", "uncovered", self.out])
        self.assertEqual(code, 0)
        items = json.loads(stdout)
        self.assertEqual([(i["kind"], i["id"]) for i in items], [("endpoint", ep["id"]), ("endpoint", "GET /other")])
        out.save(self.out, "overrides.json", {"version": 1, "drop": [], "rename": [{"id": "UC-001", "name": "N"}],
                                              "ids": {}, "merge": []})
        run_cli(["review.py", "accept", self.out, "--kind", "endpoint", "--id", ep["id"], "--reason", "dead code"])
        run_cli(["review.py", "accept", self.out, "--kind", "endpoint", "--id", ep["id"], "--reason", "out of module"])
        doc = out.load(self.out, "overrides.json")
        self.assertEqual(doc["drop"], [{"kind": "endpoint", "id": ep["id"], "reason": "out of module"}])
        self.assertEqual(doc["rename"], [{"id": "UC-001", "name": "N"}])  # a person's other corrections stay
        self.assertEqual(run_cli(["review.py", "accept", self.out, "--kind", "x", "--id", "a", "--reason", "r"])[0], 2)
        self.assertEqual(run_cli(["review.py", "accept", self.out, "--kind", "event", "--id", "a", "--reason", " "])[0], 2)

    def test_not_an_output_folder_exits_2(self):
        self.assertEqual(run_cli(["review.py", "reset", self.tmp])[0], 2)


if __name__ == "__main__":
    unittest.main()
