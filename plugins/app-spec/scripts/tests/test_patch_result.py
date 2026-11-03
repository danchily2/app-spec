import json
import os
import shutil
import tempfile
import unittest

from helpers import run_cli
from speclib import out
from test_render_catalogs import build_out

import patch_result


class TestPatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")
        self.understand = out.load(self.out, "understand_result.json")
        self.rules = out.load(self.out, "rules_result.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_understand_replace_add_remove_keep_ids(self):
        run_cli(["render.py", "catalogs", self.out])
        ids_before = out.load(self.out, "ids.json")["UC"]
        first = self.understand["useCases"][0]
        changed = {**first, "name": first["name"].upper(), "description": "corrected"}  # same normalized key
        part = {"useCases": [changed, {"name": "Share a payslip", "description": "new", "evidence": "INFERRED"}],
                "remove": [self.understand["flows"][0]["name"]] if self.understand.get("flows") else [],
                "injectionFlags": ["X.swift:1: flag"], "rejected": []}
        code, stdout, err = run_cli(["patch_result.py", self.out, "understand", self.write("p.json", part)])
        self.assertEqual(code, 0, err)
        result = out.load(self.out, "understand_result.json")
        self.assertEqual(len(result["useCases"]), len(self.understand["useCases"]) + 1)
        self.assertEqual(result["useCases"][0]["description"], "corrected")
        self.assertEqual(result["useCases"][-1]["name"], "Share a payslip")
        self.assertIn("X.swift:1: flag", result["injectionFlags"])
        self.assertEqual(result["stats"]["patches"], 1)
        self.assertEqual(result["rerunShards"], self.understand.get("rerunShards", []))
        if self.understand.get("flows"):
            self.assertEqual(len(result["flows"]), len(self.understand["flows"]) - 1)
        run_cli(["render.py", "catalogs", self.out])
        ids_after = out.load(self.out, "ids.json")["UC"]
        for key, ident in ids_before.items():
            self.assertEqual(ids_after[key], ident)

    def test_remove_also_takes_an_entry_out_of_the_out_of_scope_list(self):
        # payslips v7b MANUAL_STEPS.md: the critic raised year-end items listed out of scope in all 3 passes; the
        # mapper sent their names in `remove`, but remove reached only useCases, screens and flows
        result = out.load(self.out, "understand_result.json")
        result["outOfScope"] = [{"name": "View a year-end report (CAP-229)", "reason": "touch file"},
                                {"name": "Switch account", "reason": "accounts module"}]
        out.save(self.out, "understand_result.json", result)
        rules = out.load(self.out, "rules_result.json")
        rules["outOfScope"] = [{"name": "Year-end PDF is saved", "source": "R.swift:1", "reason": "x"},
                               {"name": "Week starts Monday", "source": "C.swift:1", "reason": "x"}]
        out.save(self.out, "rules_result.json", rules)
        code, _, err = run_cli(["patch_result.py", self.out, "understand",
                                self.write("u.json", {"remove": ["View a year-end report"]})])
        self.assertEqual(code, 0, err)
        code, _, err = run_cli(["patch_result.py", self.out, "rules",
                                self.write("r2.json", {"remove": ["Year-end PDF is saved"]})])
        self.assertEqual(code, 0, err)
        self.assertEqual([o["name"] for o in out.load(self.out, "understand_result.json")["outOfScope"]], ["Switch account"])
        self.assertEqual([o["name"] for o in out.load(self.out, "rules_result.json")["outOfScope"]], ["Week starts Monday"])

    def test_rules_match_by_name_and_source_file_and_rerun_shards_replace(self):
        rule = self.rules["rules"][0]
        same = {**rule, "source": rule["source"].split(":")[0] + ":1-2", "priority": "P0"}
        other_file = {**rule, "source": "Other/File.swift:3"}
        part = {"rules": [same, other_file], "rerunShards": ["core-02"]}
        code, _, err = run_cli(["patch_result.py", self.out, "rules", self.write("r.json", part)])
        self.assertEqual(code, 0, err)
        result = out.load(self.out, "rules_result.json")
        self.assertEqual(len(result["rules"]), len(self.rules["rules"]) + 1)
        self.assertEqual(result["rules"][0]["priority"], "P0")
        self.assertEqual(result["rerunShards"], ["core-02"])

    def test_rerun_patch_unions_evidence_and_replaces_scalars(self):
        first = self.understand["useCases"][0]
        partial = {"name": first["name"], "description": "from the re-run shard", "evidence": "INFERRED",
                   "files": ["Other/Shard.swift:4"], "endpoints": ["GET /extra"], "screens": [],
                   "strings": list(first.get("strings") or [])[:1]}
        patch = self.write("u.json", {"useCases": [partial], "rerunShards": []})
        code, _, err = run_cli(["patch_result.py", self.out, "understand", patch, "--rerun"])
        self.assertEqual(code, 0, err)
        merged = out.load(self.out, "understand_result.json")["useCases"][0]
        self.assertEqual(merged["description"], "from the re-run shard")
        self.assertEqual(merged["evidence"], "INFERRED")
        for key in ("screens", "files", "endpoints", "events", "strings", "storage", "platform", "permissions"):
            for value in first.get(key) or []:
                self.assertIn(value, merged[key], key)  # nothing the first run found is lost
        self.assertIn("Other/Shard.swift:4", merged["files"])
        self.assertIn("GET /extra", merged["endpoints"])
        self.assertEqual(len(merged["strings"]), len(set(merged["strings"])))

    def test_review_patch_still_replaces(self):
        first = self.understand["useCases"][0]
        part = {"useCases": [{"name": first["name"], "description": "fixed", "evidence": "VERIFIED", "files": []}]}
        run_cli(["patch_result.py", self.out, "understand", self.write("v.json", part)])
        self.assertEqual(out.load(self.out, "understand_result.json")["useCases"][0]["files"], [])

    def test_bad_input_exits_2(self):
        self.assertEqual(run_cli(["patch_result.py", self.out, "other", self.write("x.json", {})])[0], 2)
        self.assertEqual(run_cli(["patch_result.py", self.out, "rules", self.write("y.json", [1])])[0], 2)
        os.remove(os.path.join(self.out, "rules_result.json"))
        self.assertEqual(run_cli(["patch_result.py", self.out, "rules", self.write("z.json", {})])[0], 2)


if __name__ == "__main__":
    unittest.main()
