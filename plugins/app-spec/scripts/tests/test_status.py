import json
import os
import shutil
import tempfile
import time
import unittest

from helpers import FIX, SCRIPTS, run_cli
from speclib import out
from test_render_catalogs import build_out

import render
import status

ORDER = ("app-spec.json", "module.json", "inventory.json", "fields.json", "understand_result.json",
         "rules_result.json", "use-cases.json", "screens.json", "flows.json", "rules.json", "endpoints.json",
         "overrides.json", "prose.json", "ledger.json", "SPEC.md", "grade.json", "review.json")  # each pass: ledger, spec, grade
BASE = time.time() - 10_000


def stamp(dest, name, offset):
    """Set the modification time of `name` to BASE + offset seconds."""
    os.utime(os.path.join(dest, name), (BASE + offset, BASE + offset))


def settle(dest):
    """Give every pipeline file a modification time in pipeline order, 10 seconds apart."""
    for i, name in enumerate(ORDER):
        if os.path.exists(os.path.join(dest, name)):
            stamp(dest, name, i * 10)


def touch(dest, name, later=True):
    """Make `name` newer than every settled file (later) or older than all of them."""
    stamp(dest, name, 5_000 if later else -5_000)


def cmd(dest):
    return status.report(dest)["next"]["command"]


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def good(self, name="good", review=True, with_ledger=True, blocking=False):
        """The ios fixture through catalogs, ledger, spec, grade and review passes: the last pass is clean unless
        `blocking`, which leaves one Blocker and one High finding."""
        dest = build_out(self.tmp, name)
        render.catalogs(dest)
        if with_ledger:
            out.save(dest, "ledger.json", {"version": 1, "pass": True, "thresholds": {}, "classes": {
                "screens": {"total": 4, "covered": 4, "withReason": 0, "percent": 100, "pass": True, "uncovered": []},
                "strings": {"total": 10, "covered": 9, "withReason": 0, "percent": 90, "pass": False, "uncovered": []}}})
        render.spec(dest)
        if with_ledger:
            out.save(dest, "grade.json", {"version": 1, "checks": [], "pass": True})
        if review:
            last = [{"severity": "Blocker", "section": "Screens", "finding": "x", "fix": "y", "owner": "a"},
                    {"severity": "High", "section": "Rules", "finding": "x", "fix": "y", "owner": "a"}] if blocking else []
            out.save(dest, "review.json", {"passes": [
                {"n": 1, "ledger": {"pass": True}, "grade": {"pass": True}, "critic": [
                    {"severity": "High", "section": "Screens", "finding": "x", "fix": "y", "owner": "spec-writer"}]},
                {"n": 2, "ledger": {"pass": True}, "grade": {"pass": True}, "critic": last + [
                    {"severity": "Medium", "section": "Rules", "finding": "x", "fix": "y", "owner": "a"}]}]})
        settle(dest)
        return dest

    def test_empty_out_next_is_module(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        r = status.report(empty)
        self.assertIn("module.py", r["next"]["command"])
        self.assertIn("--out", r["next"]["command"])
        self.assertTrue(r["next"]["command"].startswith('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/module.py"'))
        self.assertTrue(all(s["status"] == "-" for n, s in r["stages"].items() if n != "contracts"))  # no contracts: vacuous

    def test_after_spec_without_review_next_is_review(self):
        dest = self.good(review=False)
        self.assertIn("review", cmd(dest))
        self.assertEqual(cmd(dest), f"/app-spec:review {dest}")

    def test_stale_spec_detected(self):
        dest = self.good()
        touch(dest, "use-cases.json", later=True)
        stale = status.report(dest)["stale"]
        self.assertTrue(any("spec predates" in s for s in stale))
        self.assertIn("the spec predates use-cases.json: re-run render.py spec", stale)

    def test_complete_next_is_a_person(self):
        dest = self.good()
        r = status.report(dest)
        self.assertEqual(r["stale"], [])
        self.assertTrue(r["next"]["command"].startswith("(a person)"))
        self.assertEqual(r["next"]["command"], "(a person) read SPEC.md")
        self.assertEqual(r["next"]["reason"], "the spec is ready for a person")

    def test_each_stage_next_command_in_order(self):
        src = build_out(self.tmp, "full")
        render.catalogs(src)
        render.spec(src)
        walk = os.path.join(self.tmp, "walk")
        os.makedirs(walk)
        self.assertIn("module.py", cmd(walk))
        steps = [("module.json", "inventory.py"), ("inventory.json", "/app-spec:spec"),
                 ("understand_result.json", "/app-spec:spec"), ("rules_result.json", 'render.py" catalogs'),
                 ("use-cases.json", 'render.py" spec'), ("SPEC.md", "/app-spec:review")]
        for name, expected in steps:
            shutil.copy(os.path.join(src, name), os.path.join(walk, name))
            settle(walk)
            self.assertIn(expected, cmd(walk), name)

    def test_understand_and_rules_texts(self):
        dest = os.path.join(self.tmp, "partial")
        os.makedirs(dest)
        for n in ("module.json", "inventory.json"):
            out.save(dest, n, {})
        self.assertEqual(cmd(dest), "/app-spec:spec " + dest + "  (run the understand workflow from /app-spec:spec)")
        out.save(dest, "understand_result.json", {})
        self.assertEqual(cmd(dest), "/app-spec:spec " + dest + "  (run the rules workflow from /app-spec:spec)")

    def test_module_command_uses_the_configured_app(self):
        dest = os.path.join(self.tmp, "cfg")
        out.save(dest, "app-spec.json", {"version": 1, "app": {"path": "/x/app"}, "module": {"query": ["payslips"]}})
        c = cmd(dest)
        self.assertIn("/x/app", c)
        self.assertIn("--module payslips", c)

    def test_contracts_done_and_undone(self):
        dest = self.good(review=False)
        cfg = out.load_config(dest)
        cfg["contracts"] = [{"path": "/b", "name": "api", "commit": "abc"}, {"path": "/c", "name": "auth", "commit": None}]
        out.save(dest, "app-spec.json", cfg)
        settle(dest)
        r = status.report(dest)
        self.assertEqual(r["stages"]["contracts"]["status"], "-")
        self.assertIn('contracts.py" ' + dest, r["next"]["command"])
        eps = out.load(dest, "endpoints.json")
        eps["endpoints"][0]["backend"] = {"repo": "api", "file": "f", "line": 1, "auth": "x"}
        eps["contractsRun"] = [{"repo": "api", "at": "2026-10-31T00:00:00Z"}]
        out.save(dest, "endpoints.json", eps)
        settle(dest)
        self.assertEqual(status.report(dest)["stages"]["contracts"]["status"], "-", "one of two repositories read")
        eps["contractsRun"].append({"repo": "auth", "at": "2026-10-31T00:00:00Z"})
        out.save(dest, "endpoints.json", eps)
        self.assertEqual(status.report(dest)["stages"]["contracts"]["status"], "done")

    def test_contracts_done_when_no_route_matched(self):
        """A contract repository with no matching route must not loop on contracts.py."""
        dest = self.good(review=False)
        cfg = out.load_config(dest)
        cfg["contracts"] = [{"path": str(FIX / "backend-empty"), "name": "backend-empty", "commit": None}]
        out.save(dest, "app-spec.json", cfg)
        self.assertEqual(run_cli(["contracts.py", dest])[0], 0)
        self.assertTrue(all(e["backend"] is None and not e.get("disagreements")
                            for e in out.load(dest, "endpoints.json")["endpoints"]))
        self.assertEqual(status.report(dest)["stages"]["contracts"]["status"], "done")
        self.assertNotIn("contracts.py", cmd(dest))

    def test_no_contracts_means_done(self):
        self.assertEqual(status.report(self.good())["stages"]["contracts"]["status"], "done")

    def test_tests_and_compare_never_block(self):
        r = status.report(self.good())
        self.assertEqual(r["stages"]["tests"]["status"], "-")
        self.assertEqual(r["stages"]["compare"]["status"], "-")
        self.assertTrue(r["next"]["command"].startswith("(a person)"))

    def test_single_agent_independence_is_in_the_status_summary(self):
        dest = self.good()
        config = out.load_config(dest)
        config["options"]["independence"] = "single-agent"
        out.save(dest, "app-spec.json", config)
        report = status.report(dest)
        self.assertEqual(report["independence"], "single-agent")
        code, stdout, err = run_cli(["status.py", dest], module=status)
        self.assertEqual(code, 0, err)
        self.assertIn("  independence: single-agent", stdout)

    def test_child_sessions_has_no_single_agent_status_line(self):
        dest = self.good()
        config = out.load_config(dest)
        config["options"]["independence"] = "child-sessions"
        out.save(dest, "app-spec.json", config)
        report = status.report(dest)
        self.assertNotIn("independence", report)
        code, stdout, err = run_cli(["status.py", dest], module=status)
        self.assertEqual(code, 0, err)
        self.assertNotIn("independence:", stdout)

    def test_inventory_and_catalog_staleness(self):
        dest = self.good()
        touch(dest, "module.json", later=True)
        self.assertIn("the inventory predates module.json: re-run inventory.py", status.report(dest)["stale"])
        self.assertIn("inventory.py", cmd(dest))
        dest = self.good("g2")
        touch(dest, "understand_result.json", later=True)
        self.assertIn("the catalogs predate understand_result.json: re-run render.py catalogs", status.report(dest)["stale"])
        self.assertIn('render.py" catalogs', cmd(dest))

    def test_stale_catalog_next_is_ledger_then_render_spec(self):
        dest = self.good()
        touch(dest, "screens.json", later=True)
        self.assertIn('ledger.py" ', cmd(dest))
        stamp(dest, "ledger.json", 5_010)
        self.assertIn('render.py" spec', cmd(dest))

    def test_review_stale(self):
        dest = self.good()
        touch(dest, "SPEC.md", later=True)
        stale = status.report(dest)["stale"]
        self.assertIn("the review predates the spec: run review", stale)
        self.assertEqual(cmd(dest), f"/app-spec:review {dest}")

    def test_ledger_and_grade_staleness(self):
        dest = self.good()
        touch(dest, "SPEC.md", later=True)
        stale = status.report(dest)["stale"]
        self.assertNotIn("the ledger predates the spec: run ledger.py", stale)  # the ledger does not read the spec
        self.assertIn("the grade predates the spec: run grade.py", stale)
        dest = self.good("g2")
        touch(dest, "use-cases.json", later=True)
        self.assertIn("the ledger predates use-cases.json: run ledger.py", status.report(dest)["stale"])
        dest = self.good("g3")
        out.save(dest, "overrides.json", {"version": 1, "drop": [], "rename": [], "ids": {}, "merge": []})
        touch(dest, "overrides.json", later=True)
        stale = status.report(dest)["stale"]
        self.assertIn("the ledger predates overrides.json: run ledger.py", stale)
        self.assertIn("the spec predates overrides.json: re-run render.py spec", stale)
        self.assertIn("ledger.py", cmd(dest), "the ledger runs before the spec it feeds")

    def test_spec_rendered_before_the_ledger_is_stale(self):
        """Appendix F reads ledger.json: a spec rendered before the ledger shows no coverage."""
        dest = build_out(self.tmp, "early")
        render.catalogs(dest)
        render.spec(dest)
        out.save(dest, "ledger.json", {"version": 1, "pass": True, "thresholds": {}, "classes": {}})
        out.save(dest, "grade.json", {"version": 1, "checks": [], "pass": True})
        out.save(dest, "review.json", {"passes": [{"n": 1, "ledger": {"pass": True}, "grade": {"pass": True}, "critic": []}]})
        settle(dest)
        stamp(dest, "ledger.json", 145)  # written after the spec, as the old pass order did
        self.assertIn("the spec predates ledger.json: re-run render.py spec", status.report(dest)["stale"])
        self.assertIn('render.py" spec', cmd(dest))

    def test_a_ledger_rerun_with_the_same_coverage_does_not_stale_the_spec(self):
        """The review command runs ledger.py after the spec; the same numbers must not send the user back to render."""
        dest = self.good()
        stamp(dest, "ledger.json", 145)
        self.assertEqual(status.report(dest)["stale"], [])

    def test_prose_newer_than_the_spec_is_stale(self):
        dest = self.good()
        out.save(dest, "prose.json", {"summary": "x"})
        touch(dest, "prose.json", later=True)
        self.assertIn("the spec predates prose.json: re-run render.py spec", status.report(dest)["stale"])
        self.assertIn('render.py" spec', cmd(dest))

    def test_failing_gates_send_the_user_to_review(self):
        dest = self.good(blocking=True)
        r = status.report(dest)
        self.assertEqual(r["next"]["command"], f"/app-spec:review {dest}")
        self.assertIn("2 Blocker/High finding(s) remain", r["next"]["reason"])
        dest = self.good("led")
        led = out.load(dest, "ledger.json")
        led["pass"] = False
        out.save(dest, "ledger.json", led)
        render.spec(dest)
        settle(dest)
        r = status.report(dest)
        self.assertEqual(r["stale"], [])
        self.assertEqual(r["next"]["command"], f"/app-spec:review {dest}")
        self.assertIn("the ledger fails (strings)", r["next"]["reason"])
        dest = self.good("gr")
        out.save(dest, "grade.json", {"version": 1, "pass": False, "checks": [
            {"name": "citations-resolve", "pass": False, "detail": "x"}, {"name": "sections", "pass": True, "detail": ""}]})
        settle(dest)
        r = status.report(dest)
        self.assertEqual(r["next"]["command"], f"/app-spec:review {dest}")
        self.assertIn("the grade fails (citations-resolve)", r["next"]["reason"])

    def test_one_second_tolerance(self):
        dest = self.good()
        spec_t = os.path.getmtime(os.path.join(dest, "SPEC.md"))
        os.utime(os.path.join(dest, "ledger.json"), (spec_t, spec_t))  # one pass writes the ledger and the spec together
        os.utime(os.path.join(dest, "use-cases.json"), (spec_t + 0.9, spec_t + 0.9))
        self.assertEqual(status.report(dest)["stale"], [])
        os.utime(os.path.join(dest, "use-cases.json"), (spec_t + 1.5, spec_t + 1.5))
        self.assertTrue(status.report(dest)["stale"])

    def test_spec_name_honoured(self):
        dest = self.good(review=False)
        cfg = out.load_config(dest)
        cfg["options"] = {"specName": "docs/specs/payslips.md"}
        out.save(dest, "app-spec.json", cfg)
        os.remove(os.path.join(dest, "SPEC.md"))
        self.assertEqual(status.report(dest)["stages"]["spec"]["status"], "-")
        self.assertTrue(cmd(dest).endswith('render.py" spec ' + dest + " --name docs/specs/payslips.md"))
        render.spec(dest, "docs/specs/payslips.md")
        settle(dest)
        stamp(dest, "docs/specs/payslips.md", 115)
        r = status.report(dest)
        self.assertEqual(r["stages"]["spec"]["status"], "done")
        self.assertIn("/app-spec:review", r["next"]["command"])

    def test_spec_name_in_grade_and_stale_render_commands(self):
        dest = self.good()
        cfg = out.load_config(dest)
        cfg["options"] = {"specName": "my spec.md"}
        out.save(dest, "app-spec.json", cfg)
        shutil.copy(os.path.join(dest, "SPEC.md"), os.path.join(dest, "my spec.md"))
        settle(dest)
        stamp(dest, "ledger.json", 115)
        stamp(dest, "my spec.md", 125)
        stamp(dest, "grade.json", 120)
        c = cmd(dest)
        self.assertTrue(c.endswith('grade.py" ' + dest + " --name 'my spec.md'"), c)
        stamp(dest, "screens.json", 200)
        stamp(dest, "ledger.json", 210)
        c = cmd(dest)
        self.assertTrue(c.endswith('render.py" spec ' + dest + " --name 'my spec.md'"), c)

    def test_malformed_config_does_not_crash(self):
        dest = os.path.join(self.tmp, "bad")
        out.save(dest, "app-spec.json", {"app": "x", "module": 3, "options": []})
        r = status.report(dest)
        self.assertEqual(r["spec"], "SPEC.md")
        self.assertIn("module.py", r["next"]["command"])
        out.save(dest, "app-spec.json", {"app": {"path": 5}, "options": {"specName": 7}})
        self.assertIn("module.py", status.report(dest)["next"]["command"])

    def test_spec_name_in_person_line(self):
        dest = self.good()
        cfg = out.load_config(dest)
        cfg["options"] = {"specName": "payslips.md"}
        out.save(dest, "app-spec.json", cfg)
        shutil.copy(os.path.join(dest, "SPEC.md"), os.path.join(dest, "payslips.md"))
        settle(dest)
        stamp(dest, "payslips.md", 115)
        self.assertEqual(cmd(dest), "(a person) read payslips.md")

    def test_coverage_and_passes(self):
        r = status.report(self.good(blocking=True))
        self.assertEqual(r["coverage"], {"screens": 100, "strings": 90})
        self.assertEqual(r["passes"], 2)
        self.assertEqual(r["blocking"], 2)

    def test_no_ledger_no_review(self):
        r = status.report(self.good(review=False, with_ledger=False))
        self.assertIsNone(r["coverage"])
        self.assertEqual(r["passes"], 0)

    def test_cli_text_and_json(self):
        dest = self.good()
        code, text, _ = run_cli(["status.py", dest])
        self.assertEqual(code, 0)
        self.assertIn("review", text)
        self.assertIn("Next: (a person) read SPEC.md", text)
        self.assertIn("screens 100%", text)
        code, text, _ = run_cli(["status.py", dest, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["next"]["command"], "(a person) read SPEC.md")

    def test_cli_exit_code_for_non_output_folder(self):
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        out.save_text(other, "notes.txt", "hi")
        code, _, err = run_cli(["status.py", other])
        self.assertEqual(code, 2)
        self.assertIn("not an app-spec output folder", err)
        code, _, _ = run_cli(["status.py", os.path.join(other, "notes.txt")])
        self.assertEqual(code, 2)

    def test_cli_exit_zero_when_work_remains(self):
        empty = os.path.join(self.tmp, "e")
        os.makedirs(empty)
        self.assertEqual(run_cli(["status.py", empty])[0], 0)


class TestSkillPassOrder(unittest.TestCase):
    def test_each_pass_runs_ledger_then_spec_then_grade(self):
        """Appendix F of the spec reads ledger.json, so the ledger must run before the spec is rendered."""
        path = SCRIPTS.parent / "skills" / "spec" / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        step = text[text.index("## 7:"):text.index("## 8:")]
        ledger, spec, grade = (step.index(x) for x in ('scripts/ledger.py" OUT', 'scripts/render.py" spec OUT',
                                                       'scripts/grade.py" OUT'))
        self.assertLess(ledger, spec)
        self.assertLess(spec, grade)


if __name__ == "__main__":
    unittest.main()
