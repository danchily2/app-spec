import json
import os
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out

import inventory
import render

IOS = str(FIX / "ios-app")
RESULTS = FIX / "results"
LIST_VIEW = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift"


def build_out(tmp, name, index=None):
    """An output folder for the ios fixture with both inventory files and the two workflow results copied in."""
    dest = os.path.join(tmp, name)
    code, _, err = run_cli(["module.py", IOS, "--module", "Payslips", "--out", dest])
    assert code == 0, err
    inventory.run(dest)
    for f in ("understand_result.json", "rules_result.json"):
        shutil.copy(RESULTS / f, os.path.join(dest, f))
    if index:
        cfg = out.load_config(dest)
        cfg["capabilityIndex"] = str(index)
        out.save(dest, "app-spec.json", cfg)
    return dest


def read_text(dest, name):
    with open(os.path.join(dest, name), encoding="utf-8") as fh:
        return fh.read()


def write_overrides(dest, data):
    out.save(dest, "overrides.json", {"version": 1, "drop": [], "rename": [], "ids": {}, "merge": [], **data})


class TestCatalogs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def uc(self, dest, name):
        return next(u for u in out.load(dest, "use-cases.json")["useCases"] if u["name"] == name)

    def test_catalogs_rerun_keeps_ids(self):
        render.catalogs(self.out)
        first = {n: out.load(self.out, n) for n in ("use-cases.json", "screens.json", "flows.json", "rules.json",
                                                    "endpoints.json", "ids.json")}
        render.catalogs(self.out)
        for name, data in first.items():
            self.assertEqual(out.load(self.out, name), data, name)

    def test_rerun_keeps_ids_when_the_result_order_changes(self):
        render.catalogs(self.out)
        before = {u["name"]: u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]}
        result = out.load(self.out, "understand_result.json")
        result["useCases"].reverse()
        out.save(self.out, "understand_result.json", result)
        render.catalogs(self.out)
        after = {u["name"]: u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]}
        self.assertEqual(before, after)

    def test_a_new_use_case_takes_the_next_number_and_a_dropped_one_is_not_reused(self):
        render.catalogs(self.out)
        result = out.load(self.out, "understand_result.json")
        gone = result["useCases"].pop(0)  # UC-001 leaves the result
        result["useCases"].append({**result["useCases"][0], "name": "Brand new outcome"})
        out.save(self.out, "understand_result.json", result)
        render.catalogs(self.out)
        by_name = {u["name"]: u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]}
        self.assertNotIn(gone["name"], by_name)
        self.assertEqual(by_name["Brand new outcome"], "UC-004")
        self.assertEqual(out.load(self.out, "ids.json")["UC"]["view payslip list"], "UC-001")

    def test_use_cases_hold_ids_and_drop_rules_hint(self):
        render.catalogs(self.out)
        uc = self.uc(self.out, "View payslip list")
        self.assertEqual(uc["id"], "UC-001")
        self.assertIsNone(uc["alias"])
        self.assertNotIn("rulesHint", uc)
        self.assertTrue(all(s.startswith("SCR-") for s in uc["screens"]))
        self.assertEqual(len(uc["endpoints"]), 1)
        self.assertTrue(uc["endpoints"][0].startswith("EP-"))

    def test_screens_copy_fields_by_file_and_propose_ids(self):
        render.catalogs(self.out)
        screens = {s["name"]: s for s in out.load(self.out, "screens.json")["screens"]}
        listing = screens["PayslipListView"]
        self.assertEqual(listing["file"], f"{LIST_VIEW}:3")
        self.assertEqual([u.startswith("UC-") for u in listing["useCases"]], [True, True])
        by_line = {e["line"]: e for e in listing["elements"]}
        self.assertEqual(by_line[8]["proposedId"], "pay.list.title")  # the old identifier is kept
        slug = "PayslipListView".lower()
        self.assertEqual(by_line[10]["proposedId"], f"payslips.{slug}.list-1")  # kind and index: no key, no text
        self.assertEqual(by_line[12]["proposedId"], f"payslips.{slug}.refresh")  # literal text
        self.assertEqual(by_line[14]["proposedId"], f"payslips.{slug}.open")  # confirmed by the analyst, absent from fields.json
        self.assertEqual(len(listing["elements"]), 4)
        self.assertTrue(all(e["proposedId"] for e in listing["elements"]))

    def test_flows_and_rules_use_ids(self):
        render.catalogs(self.out)
        flow = out.load(self.out, "flows.json")["flows"][0]
        self.assertEqual(flow["id"], "FLOW-001")
        self.assertTrue(all(s["screen"].startswith("SCR-") and s["useCases"][0].startswith("UC-") for s in flow["steps"]))
        rules = out.load(self.out, "rules.json")["rules"]
        self.assertEqual([r["id"] for r in rules], ["RULE-001", "RULE-002"])
        self.assertEqual(rules[0]["useCase"], "UC-001")
        self.assertIsNone(rules[1]["useCase"])
        self.assertEqual(out.load(self.out, "ids.json")["RULE"]["payslips are newest first|Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift"], "RULE-001")

    def test_endpoint_label_unknown_when_unresolved(self):
        render.catalogs(self.out)
        eps = out.load(self.out, "endpoints.json")["endpoints"]
        e = next(x for x in eps if "{}" in x["path"] and not x["useCases"])
        self.assertEqual(e["label"], "UNKNOWN")
        self.assertIsNone(e["backend"])

    def test_endpoint_verified_when_a_use_case_cites_it_with_the_client_file(self):
        render.catalogs(self.out)
        eps = out.load(self.out, "endpoints.json")["endpoints"]
        self.assertEqual(len(eps), 2)  # one per inventory endpoint
        e = next(x for x in eps if x["path"].endswith("/payslips"))
        self.assertEqual(e["label"], "VERIFIED")
        self.assertEqual(e["useCases"], ["UC-001"])
        self.assertEqual(e["client"], {"file": "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift", "type": "GetPayslips"})
        self.assertEqual(out.load(self.out, "ids.json")["EP"]["GET /employee/api/v1/employees/{}/payslips"], e["id"])

    def test_endpoint_inferred_when_cited_without_the_client_file(self):
        result = out.load(self.out, "understand_result.json")
        result["useCases"][0]["files"] = [LIST_VIEW]
        out.save(self.out, "understand_result.json", result)
        render.catalogs(self.out)
        e = next(x for x in out.load(self.out, "endpoints.json")["endpoints"] if x["path"].endswith("/payslips"))
        self.assertEqual(e["label"], "INFERRED")

    def test_override_merge_folds_use_case(self):
        write_overrides(self.out, {"merge": [{"into": "UC-001", "from": ["UC-002"]}]})
        render.catalogs(self.out)
        cases = out.load(self.out, "use-cases.json")["useCases"]
        self.assertNotIn("UC-002", [u["id"] for u in cases])
        into = next(u for u in cases if u["id"] == "UC-001")
        self.assertIn("SCR-002", into["screens"])  # the detail screen came along
        flow = out.load(self.out, "flows.json")["flows"][0]
        self.assertNotIn("UC-002", json.dumps(flow))
        self.assertEqual(out.load(self.out, "ids.json")["UC"]["view payslip s details"], "UC-002")  # retired, never reused

    def test_override_rename_changes_the_name_not_the_id(self):
        write_overrides(self.out, {"rename": [{"id": "UC-001", "name": "See my payslips"}]})
        render.catalogs(self.out)
        case = next(u for u in out.load(self.out, "use-cases.json")["useCases"] if u["id"] == "UC-001")
        self.assertEqual(case["name"], "See my payslips")
        render.catalogs(self.out)
        self.assertEqual(out.load(self.out, "ids.json")["UC"]["view payslip list"], "UC-001")

    def test_overrides_ids_set_the_proposed_id(self):
        write_overrides(self.out, {"ids": {"SCR-001.title": "custom.title"}})
        render.catalogs(self.out)
        listing = next(s for s in out.load(self.out, "screens.json")["screens"] if s["id"] == "SCR-001")
        self.assertEqual(next(e for e in listing["elements"] if e["line"] == 8)["proposedId"], "custom.title")

    def test_catalogs_leave_overrides_and_config_alone(self):
        write_overrides(self.out, {"rename": [{"id": "UC-001", "name": "X"}]})
        names = ("overrides.json", "app-spec.json")
        before = [read_text(self.out, n) for n in names]
        render.catalogs(self.out)
        after = [read_text(self.out, n) for n in names]
        self.assertEqual(before, after)

    def test_cli_runs_catalogs(self):
        code, stdout, err = run_cli(["render.py", "catalogs", self.out], module=render)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(self.out, "use-cases.json")))

    def test_missing_understand_result_exits_2(self):
        os.remove(os.path.join(self.out, "understand_result.json"))
        code, _, err = run_cli(["render.py", "catalogs", self.out], module=render)
        self.assertEqual(code, 2)
        self.assertIn("understand_result.json", err)


class TestAlias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.dest = build_out(cls.tmp, "indexed", index=RESULTS / "capability_index_alias.json")
        render.catalogs(cls.dest)
        cls.cases = {u["name"]: u for u in out.load(cls.dest, "use-cases.json")["useCases"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_catalog_alias_from_index(self):
        self.assertEqual(self.cases["View a payslip's details"]["alias"], "CAP-225")

    def test_alias_by_shared_files_picks_the_largest_overlap(self):
        self.assertEqual(self.cases["View payslip list"]["alias"], "CAP-226")

    def test_a_name_match_wins_over_a_file_match(self):
        self.assertEqual(self.cases["Refresh the payslip list"]["alias"], "CAP-300")  # CAP-227 shares a file too

    def test_a_capability_aliases_at_most_one_use_case(self):
        aliases = [u["alias"] for u in self.cases.values() if u["alias"]]
        self.assertEqual(len(aliases), len(set(aliases)))

    def test_capability_of_another_app_is_ignored(self):
        self.assertNotIn("CAP-310", [u["alias"] for u in self.cases.values()])


if __name__ == "__main__":
    unittest.main()
