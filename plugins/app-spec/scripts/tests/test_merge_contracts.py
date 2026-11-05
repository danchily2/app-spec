import json
import os
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out
from test_render_catalogs import build_out, read_text

import merge_contracts

ASPNET = str(FIX / "backend-aspnet")
FIELDS = {"fields": [{"name": "gross", "type": "decimal", "required": False, "nullable": "explicit"}]}


def endpoints(dest):
    return {e["id"]: e for e in out.load(dest, "endpoints.json")["endpoints"]}


class TestLabel(unittest.TestCase):
    def test_verified_stays_unless_unknown_with_reason(self):
        self.assertEqual(merge_contracts.label("VERIFIED", "INFERRED", None), "VERIFIED")
        self.assertEqual(merge_contracts.label("VERIFIED", "UNKNOWN", None), "VERIFIED")
        self.assertEqual(merge_contracts.label("VERIFIED", "UNKNOWN", "response type not found"), "UNKNOWN")

    def test_reader_never_raises_to_verified(self):
        self.assertEqual(merge_contracts.label("INFERRED", "VERIFIED", None), "INFERRED")
        self.assertEqual(merge_contracts.label("UNKNOWN", "VERIFIED", None), "INFERRED")
        self.assertEqual(merge_contracts.label("UNKNOWN", "INFERRED", None), "INFERRED")

    def test_other_labels_can_go_down(self):
        self.assertEqual(merge_contracts.label("INFERRED", "UNKNOWN", None), "UNKNOWN")
        self.assertEqual(merge_contracts.label("INFERRED", "bogus", None), "INFERRED")


class TestMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")
        code, _, err = run_cli(["render.py", "catalogs", self.out])
        self.assertEqual(code, 0, err)
        code, _, err = run_cli(["contracts.py", self.out, "--repo", ASPNET])
        self.assertEqual(code, 0, err)
        self.ids = endpoints(self.out)
        self.verified = next(i for i, e in self.ids.items() if e["label"] == "VERIFIED")
        self.other = next(i for i, e in self.ids.items() if e["label"] != "VERIFIED")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def envelope(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_a_batch_file_saved_but_not_named_is_merged_once(self):
        # payslips v8: the session saved contracts/batch-4.json and ran `merge_contracts.py OUT` without it, so the
        # corrected error reactions never reached endpoints.json and critic-3 raised them again
        os.makedirs(os.path.join(self.out, "contracts"), exist_ok=True)
        first = os.path.join(self.out, "contracts", "batch-1.json")
        with open(first, "w", encoding="utf-8") as fh:
            json.dump({"endpoints": [{"id": self.verified, "response": FIELDS, "errors": [{"status": 500, "reaction": "old"}]}]}, fh)
        code, _, err = run_cli(["merge_contracts.py", self.out, first])
        self.assertEqual(code, 0, err)
        later = os.path.join(self.out, "contracts", "batch-4.json")
        with open(later, "w", encoding="utf-8") as fh:
            json.dump({"endpoints": [{"id": self.verified, "errors": [{"status": 500, "reaction": "corrected"}]}]}, fh)
        code, stdout, err = run_cli(["merge_contracts.py", self.out])  # no file named
        self.assertEqual(code, 0, err)
        self.assertEqual(endpoints(self.out)[self.verified]["errors"], [{"status": 500, "reaction": "corrected"}])
        self.assertIn("batch-4.json", stdout)
        # a second run without files folds nothing again: batch-1 never overwrites the correction
        code, _, err = run_cli(["merge_contracts.py", self.out])
        self.assertEqual(code, 0, err)
        self.assertEqual(endpoints(self.out)[self.verified]["errors"], [{"status": 500, "reaction": "corrected"}])

    def test_fields_disagreements_and_flags_are_merged(self):
        env = self.envelope("a.json", {
            "endpoints": [{"id": self.verified, "request": {"fields": []}, "response": FIELDS,
                           "errors": [{"status": 404, "reaction": "shows the not-found state"}],
                           "auth": "bearer token", "label": "INFERRED", "citations": ["A.swift:3"]},
                          {"id": "EP-999", "label": "INFERRED"}],
            "disagreements": [{"endpoint": self.verified, "field": "gross", "client": "A.swift:3",
                               "backend": "B.cs:9", "note": "nullable on the client only"}],
            "injectionFlags": ["A.swift:7: ignore your rules"]})
        code, stdout, err = run_cli(["merge_contracts.py", self.out, env])
        self.assertEqual(code, 0, err)
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["response"], FIELDS)
        self.assertEqual(e["errors"][0]["status"], 404)
        self.assertEqual(e["auth"], "bearer token")
        self.assertEqual(e["label"], "VERIFIED")  # the reader's INFERRED does not lower contracts.py's VERIFIED
        self.assertEqual(e["disagreements"], [{"field": "gross", "client": "A.swift:3", "backend": "B.cs:9",
                                               "note": "nullable on the client only"}])
        self.assertIn("EP-999: not in endpoints.json", err)
        self.assertIn("injection flag: A.swift:7", stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.out, merge_contracts.RESULT)))

    def test_unknown_with_reason_lowers_verified_and_keeps_the_reason(self):
        env = self.envelope("a.json", {"endpoints": [{"id": self.verified, "label": "UNKNOWN",
                                                      "reason": "the response fields are generated, not in the repo"}]})
        run_cli(["merge_contracts.py", self.out, env])
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["label"], "UNKNOWN")
        self.assertEqual(e["reason"], "the response fields are generated, not in the repo")

    def test_a_reason_that_names_no_field_keeps_verified(self):
        env = self.envelope("a.json", {"endpoints": [{"id": self.verified, "label": "UNKNOWN",
                                                      "reason": "could not tell", "response": FIELDS}]})
        run_cli(["merge_contracts.py", self.out, env])
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["label"], "VERIFIED")
        self.assertNotIn("reason", e)

    def test_a_reason_that_names_a_field_of_the_entry_lowers_verified(self):
        env = self.envelope("a.json", {"endpoints": [{"id": self.verified, "label": "UNKNOWN", "response": FIELDS,
                                                      "reason": "gross is decoded but never declared"}]})
        run_cli(["merge_contracts.py", self.out, env])
        self.assertEqual(endpoints(self.out)[self.verified]["label"], "UNKNOWN")

    def test_reapply_after_render_restores_the_merge_and_is_idempotent(self):
        env = self.envelope("a.json", {
            "endpoints": [{"id": self.verified, "response": FIELDS, "label": "VERIFIED"}],
            "disagreements": [{"endpoint": self.verified, "field": "gross", "client": "A.swift:3", "backend": "B.cs:9",
                               "note": "n"}]})
        run_cli(["merge_contracts.py", self.out, env])
        run_cli(["render.py", "catalogs", self.out])  # writes endpoints.json from scratch
        self.assertNotEqual(endpoints(self.out)[self.verified]["response"], FIELDS)
        run_cli(["contracts.py", self.out, "--repo", ASPNET])
        for _ in range(2):
            code, _, err = run_cli(["merge_contracts.py", self.out])
            self.assertEqual(code, 0, err)
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["response"], FIELDS)
        self.assertEqual(len(e["disagreements"]), 1)

    def test_a_later_batch_replaces_the_same_id(self):
        first = self.envelope("a.json", {"endpoints": [{"id": self.other, "auth": "first", "label": "INFERRED"}],
                                         "injectionFlags": ["X.swift:1: flag"]})
        second = self.envelope("b.json", {"endpoints": [{"id": self.other, "auth": "second", "label": "INFERRED"}],
                                          "injectionFlags": ["X.swift:1: flag"]})
        run_cli(["merge_contracts.py", self.out, first])
        run_cli(["merge_contracts.py", self.out, second])
        saved = out.load(self.out, merge_contracts.RESULT)
        self.assertEqual([e["auth"] for e in saved["endpoints"]], ["second"])
        self.assertEqual(saved["injectionFlags"], ["X.swift:1: flag"])
        self.assertEqual(endpoints(self.out)[self.other]["auth"], "second")

    def test_an_edited_envelope_replaces_its_disagreements(self):
        def env(name, notes):
            return self.envelope(name, {
                "endpoints": [{"id": self.verified, "label": "VERIFIED"}],
                "disagreements": [{"endpoint": self.verified, "field": f, "client": "A.swift:3", "backend": "B.cs:9",
                                   "note": n} for f, n in notes]})
        first = env("a.json", [("gross", "nullable on the client only"), ("net", "missing on the backend")])
        edited = env("a2.json", [("gross", "nullable on the client only, optional on the backend")])
        run_cli(["merge_contracts.py", self.out, first])
        self.assertEqual(len(endpoints(self.out)[self.verified]["disagreements"]), 2)
        code, _, err = run_cli(["merge_contracts.py", self.out, edited])
        self.assertEqual(code, 0, err)
        saved = out.load(self.out, merge_contracts.RESULT)
        self.assertEqual([d["note"] for d in saved["disagreements"]], ["nullable on the client only, optional on the backend"])
        self.assertEqual([d["note"] for d in endpoints(self.out)[self.verified]["disagreements"]],
                         ["nullable on the client only, optional on the backend"])
        run_cli(["merge_contracts.py", self.out])
        self.assertEqual(len(endpoints(self.out)[self.verified]["disagreements"]), 1)

    def test_the_ambiguous_route_note_of_contracts_py_stays(self):
        data = out.load(self.out, "endpoints.json")
        note = {"field": "route", "client": "A.swift", "backend": "a.cs:1 | b.cs:1", "note": "ambiguous backend route"}
        next(e for e in data["endpoints"] if e["id"] == self.other)["disagreements"] = [note]
        out.save(self.out, "endpoints.json", data)
        env = self.envelope("a.json", {"endpoints": [{"id": self.other, "label": "INFERRED"}],
                                       "disagreements": [{"endpoint": self.other, "field": "y", "note": "b"}]})
        run_cli(["merge_contracts.py", self.out, env])
        self.assertEqual([d["note"] for d in endpoints(self.out)[self.other]["disagreements"]],
                         ["ambiguous backend route", "b"])

    def test_an_envelope_for_another_endpoint_keeps_the_first_ones(self):
        a = self.envelope("a.json", {"endpoints": [{"id": self.verified, "label": "VERIFIED"}],
                                     "disagreements": [{"endpoint": self.verified, "field": "x", "note": "a"}]})
        b = self.envelope("b.json", {"endpoints": [{"id": self.other, "label": "INFERRED"}],
                                     "disagreements": [{"endpoint": self.other, "field": "y", "note": "b"}]})
        run_cli(["merge_contracts.py", self.out, a, b])
        self.assertEqual([d["note"] for d in out.load(self.out, merge_contracts.RESULT)["disagreements"]], ["a", "b"])

    def test_a_field_source_past_the_end_of_its_file_is_a_warning(self):
        bad = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift:3-70"  # a 14-line app file
        env = self.envelope("r.json", {"endpoints": [{"id": self.other, "response": {"fields": [
            {"name": "gross", "type": "decimal", "required": False, "nullable": "explicit", "source": bad}]}}],
            "disagreements": [], "injectionFlags": []})
        code, _, err = run_cli(["merge_contracts.py", self.out, env])
        self.assertEqual(code, 0, err)
        self.assertIn(f"cites {bad}: the file has", err)
        records = [r for r in out.load(self.out, "render-warnings.json") if r["kind"] == "citation"]
        self.assertEqual([r["item"] for r in records], [bad])
        # a second merge replaces its own warnings instead of adding them again
        run_cli(["merge_contracts.py", self.out])
        records = [r for r in out.load(self.out, "render-warnings.json") if r["kind"] == "citation"]
        self.assertEqual(len(records), 1)

    def test_without_a_result_nothing_changes(self):
        before = out.load(self.out, "endpoints.json")
        code, stdout, _ = run_cli(["merge_contracts.py", self.out])
        self.assertEqual(code, 0)
        self.assertIn("unchanged", stdout)
        self.assertEqual(out.load(self.out, "endpoints.json"), before)

    def test_bad_envelope_and_bad_folder_exit_2(self):
        bad = self.envelope("bad.json", ["not", "an", "envelope"])
        self.assertEqual(run_cli(["merge_contracts.py", self.out, bad])[0], 2)
        self.assertEqual(run_cli(["merge_contracts.py", self.tmp])[0], 2)
        self.assertEqual(run_cli(["merge_contracts.py"])[0], 2)


if __name__ == "__main__":
    unittest.main()


class TestCitationPaths(unittest.TestCase):
    """Readers cite root-relative, `<root folder name>/...` and absolute paths; all three merge root-relative."""

    def setUp(self):
        import test_grade
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.grade_mod = test_grade
        self.dest = test_grade.make_good(self.tmp)
        self.contract = os.path.join(self.tmp, "me-api")
        os.makedirs(os.path.join(self.contract, "Controllers"))
        with open(os.path.join(self.contract, "Controllers", "PayslipController.cs"), "w") as fh:
            fh.write("".join(f"line {i}\n" for i in range(1, 21)))
        cfg = out.load_config(self.dest)
        cfg["contracts"] = [{"path": self.contract, "name": "me-api", "commit": None}]
        out.save(self.dest, "app-spec.json", cfg)
        self.app = cfg["app"]["path"]
        self.app_name = os.path.basename(self.app)

    def test_three_path_shapes_merge_relative_and_resolve(self):
        lst = self.grade_mod.LIST
        ep = out.load(self.dest, "endpoints.json")["endpoints"][0]["id"]
        env = os.path.join(self.tmp, "batch.json")
        with open(env, "w") as fh:
            json.dump({"endpoints": [{"id": ep, "label": "INFERRED",
                                      "citations": [f"{lst}:8", f"{self.app_name}/{lst}:8", f"{self.app}/{lst}:8",
                                                    "me-api/Controllers/PayslipController.cs:12",
                                                    f"{self.contract}/Controllers/PayslipController.cs:3-4"]}],
                       "disagreements": [
                           {"endpoint": ep, "field": "id", "client": f"{self.app_name}/{lst}:8",
                            "backend": "me-api/Controllers/PayslipController.cs:12", "note": "a"},
                           {"endpoint": ep, "field": "date", "client": f"{self.app}/{lst}:8",
                            "backend": f"{self.contract}/Controllers/PayslipController.cs:3", "note": "b"}]}, fh)
        code, _, err = run_cli(["merge_contracts.py", self.dest, env])
        self.assertEqual(code, 0, err)
        saved = out.load(self.dest, merge_contracts.RESULT)
        self.assertEqual(saved["endpoints"][0]["citations"],
                         [f"{lst}:8"] * 3 + ["Controllers/PayslipController.cs:12", "Controllers/PayslipController.cs:3-4"])
        self.assertEqual({(d["client"], d["backend"]) for d in saved["disagreements"]},
                         {(f"{lst}:8", "Controllers/PayslipController.cs:12"),
                          (f"{lst}:8", "Controllers/PayslipController.cs:3")})
        import grade
        import render
        render.spec(self.dest)
        self.assertTrue(self.grade_mod.check(grade.run(self.dest), "citations-resolve")["pass"])

    def test_prose_paths_are_shown_relative(self):
        import render
        prose = out.load(self.dest, "prose.json")
        lst = self.grade_mod.LIST
        prose["summary"] = f"An employee reads their payslips. Source: `{self.app}/{lst}:8` and `{self.app_name}/{lst}:9`"
        out.save(self.dest, "prose.json", prose)
        render.spec(self.dest)
        text = read_text(self.dest, "SPEC.evidence.md")
        self.assertIn(f"Source: `{lst}:8` and `{lst}:9`", text)

    def test_a_real_folder_named_like_the_root_is_kept(self):
        from speclib import paths
        os.makedirs(os.path.join(self.contract, "me-api"))
        with open(os.path.join(self.contract, "me-api", "X.cs"), "w") as fh:
            fh.write("x\n")
        roots = paths.roots(out.load_config(self.dest))
        self.assertEqual(paths.relativize("see me-api/X.cs:1", roots), "see me-api/X.cs:1")
        self.assertEqual(paths.relativize("`~/nowhere/a/b.cs:1`", roots), "`~/nowhere/a/b.cs:1`")
