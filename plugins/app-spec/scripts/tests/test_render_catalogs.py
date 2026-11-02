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
GETTER = "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift"
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


class TestOutOfScope(unittest.TestCase):
    """Touch files are context: what has no evidence in a core file leaves the catalogs for out-of-scope.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "scope")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def edit(self, name, change):
        data = out.load(self.out, name)
        change(data)
        out.save(self.out, name, data)

    def test_touch_only_use_cases_and_rules_leave_the_catalogs(self):
        card = "Employee/StartPage/PayslipCard.swift"

        def understood(r):
            r["useCases"].append({"name": "Sign in to the app", "description": "neighbour", "files": [f"{card}:3"],
                                  "screens": [], "evidence": "VERIFIED"})
            r["screens"][0]["useCases"].append("Sign in to the app")
            r["outOfScope"] = [{"name": "Share an expense", "reason": "only the share extension implements it"}]

        def rules(r):
            r["rules"].append({**r["rules"][0], "name": "Card shows the latest payslip", "source": f"{card}:5-9"})
            r["rules"].append({**r["rules"][0], "name": "Session expires", "useCase": "Sign in to the app",
                               "source": "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift:30"})
            r["outOfScope"] = [{"name": "Calendar week starts on Monday", "reason": "calendar module"}]

        self.edit("understand_result.json", understood)
        self.edit("rules_result.json", rules)
        result = render.catalogs(self.out)
        cases = out.load(self.out, "use-cases.json")["useCases"]
        self.assertEqual(sorted(u["name"] for u in cases),
                         ["Refresh the payslip list", "View a payslip's details", "View payslip list"])
        outside = out.load(self.out, "out-of-scope.json")
        self.assertEqual(sorted(e["name"] for e in outside["useCases"]), ["Share an expense", "Sign in to the app"])
        self.assertEqual(sorted(e["name"] for e in outside["rules"]),
                         ["Calendar week starts on Monday", "Card shows the latest payslip", "Session expires"])
        self.assertTrue(all(e["id"].startswith(("UC-", "RULE-")) and e["reason"] for k in outside
                            if k != "version" for e in outside[k]))
        kept = out.load(self.out, "rules.json")["rules"]
        self.assertEqual(len(kept), 2)
        self.assertTrue(all(r["source"].startswith(("Modules/", "EmployeeServices/")) for r in kept))
        ids = {u["id"] for u in cases}
        screens = out.load(self.out, "screens.json")["screens"]
        self.assertTrue(all(set(s["useCases"]) <= ids for s in screens))
        self.assertEqual(result["outOfScope"], 5)
        self.assertNotIn("names the use case Sign in", " ".join(result["warnings"]))

        render.spec(self.out)
        text = read_text(self.out, "SPEC.md")
        line = next(x for x in text.splitlines() if x.startswith("- **Out of scope"))
        self.assertIn("Sign in to the app", line)
        self.assertIn("Calendar week starts on Monday", line)
        self.assertEqual(text.count("Sign in to the app"), 1, "named only on the out-of-scope line")


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

    # ---------------------------------------------------------------- fix round 1

    def edit(self, name, change):
        data = out.load(self.out, name)
        change(data)
        out.save(self.out, name, data)

    def warnings(self):
        return render.catalogs(self.out)["warnings"]

    def test_inventory_endpoint_clients_are_collected_and_a_second_client_verifies(self):
        def add(inv):
            first = inv["endpoints"][1]
            inv["endpoints"].append({**first, "type": "GetPayslipsV2", "file": LIST_VIEW + ":30"})
            inv["endpoints"].append({"path": "/x/{}/y", "type": "NoVerb", "file": LIST_VIEW + ":40"})
        self.edit("inventory.json", add)
        self.edit("understand_result.json", lambda r: r["useCases"][0].update(files=[LIST_VIEW]))
        warnings = self.warnings()
        eps = out.load(self.out, "endpoints.json")["endpoints"]
        self.assertEqual(len(eps), 2)
        e = next(x for x in eps if x["path"].endswith("/payslips"))
        self.assertEqual([c["type"] for c in e["clients"]], ["GetPayslips", "GetPayslipsV2"])
        self.assertEqual(e["client"], e["clients"][0])
        self.assertEqual(e["label"], "VERIFIED")  # only the second client file is in the use case's files
        self.assertEqual([w for w in warnings if "NoVerb" in w and "no method" in w and "left out" in w].__len__(), 1)

    def test_alias_and_endpoint_order_follow_the_ids_not_the_result_order(self):
        index = os.path.join(self.tmp, "contend.json")
        out.save(self.tmp, "contend.json", {"capabilities": [
            {"id": "CAP-900", "name": "Overview", "implementations": {"ios-app": {"files": [LIST_VIEW, GETTER]}}}]})
        cfg = out.load_config(self.out)
        cfg["capabilityIndex"] = index
        out.save(self.out, "app-spec.json", cfg)

        def prepare(result):
            result["useCases"][0]["files"] = [LIST_VIEW, GETTER]
            result["useCases"][2]["files"] = [LIST_VIEW]
            result["useCases"][2]["endpoints"] = ["GET /employees/{id}/payslips"]
        self.edit("understand_result.json", prepare)
        render.catalogs(self.out)
        first = (out.load(self.out, "use-cases.json"), out.load(self.out, "endpoints.json"))
        aliases = {u["id"]: u["alias"] for u in first[0]["useCases"]}
        self.assertEqual(aliases["UC-001"], "CAP-900")  # the larger overlap wins although UC-003 may be listed first
        self.assertIsNone(aliases["UC-003"])
        self.edit("understand_result.json", lambda r: r["useCases"].reverse())
        render.catalogs(self.out)
        self.assertEqual((out.load(self.out, "use-cases.json"), out.load(self.out, "endpoints.json")), first)
        e = next(x for x in first[1]["endpoints"] if x["path"].endswith("/payslips"))
        self.assertEqual(e["useCases"], ["UC-001", "UC-003"])

    def test_renamed_use_case_with_the_same_files_keeps_its_id(self):
        render.catalogs(self.out)
        self.edit("understand_result.json", lambda r: r["useCases"][0].update(name="See all my payslips"))
        render.catalogs(self.out)
        cases = {u["name"]: u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]}
        self.assertEqual(cases["See all my payslips"], "UC-001")
        self.assertEqual(len(cases), 3)
        saved = out.load(self.out, "ids.json")
        self.assertEqual(saved["UC"]["view payslip list"], "UC-001")  # the old key stays
        self.assertEqual(saved["max"]["UC"], 3)
        self.assertEqual(saved["UCfiles"]["UC-001"], sorted({LIST_VIEW, GETTER}))

    def test_a_new_use_case_with_other_files_gets_a_new_id(self):
        render.catalogs(self.out)
        self.edit("understand_result.json", lambda r: r["useCases"][0].update(name="Something else", files=[LIST_VIEW + ":1", "Other.swift"]))
        render.catalogs(self.out)
        ids_ = {u["name"]: u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]}
        self.assertEqual(ids_["Something else"], "UC-004")

    def test_warning_unknown_screen_in_use_case_flow_step_and_rule(self):
        def change(r):
            r["useCases"][0]["screens"].append("GhostScreen")
            r["flows"][0]["steps"][0]["screen"] = "GhostFlowScreen"
        self.edit("understand_result.json", change)
        self.edit("rules_result.json", lambda r: r["rules"][0].update(useCase="Ghost use case"))
        warnings = self.warnings()
        self.assertIn("use case View payslip list names the screen GhostScreen, which understand_result.json does not have", warnings)
        self.assertIn("flow Read the latest payslip names the screen GhostFlowScreen, which understand_result.json does not have", warnings)
        self.assertIn("rule Payslips are newest first names the use case Ghost use case, which understand_result.json does not have", warnings)
        self.assertEqual(len(warnings), 3)

    def test_warning_cited_endpoint_missing_from_inventory(self):
        self.edit("understand_result.json", lambda r: r["useCases"][0]["endpoints"].append("GET /nothing/here/{id}"))
        warnings = self.warnings()
        eps = out.load(self.out, "endpoints.json")["endpoints"]
        ghost = next(e for e in eps if e["path"] == "/nothing/here/{}")
        self.assertEqual(warnings, [f"use case View payslip list cites GET /nothing/here/{{id}}, which is not in the "
                                    f"inventory; kept as {ghost['id']} with label UNKNOWN"])
        self.assertEqual((ghost["method"], ghost["label"], ghost["inInventory"], ghost["clients"], ghost["useCases"]),
                         ("GET", "UNKNOWN", False, [], ["UC-001"]))
        self.assertIn("not in the inventory", ghost["reason"])
        self.assertIn(ghost["id"], self.uc(self.out, "View payslip list")["endpoints"])
        self.assertEqual(out.load(self.out, "render-warnings.json"), [
            {"kind": "endpoint", "item": "GET /nothing/here/{id}", "why": warnings[0]}])

    def test_a_cited_endpoint_missing_from_inventory_reaches_the_spec_and_the_ledger(self):
        import ledger
        self.edit("understand_result.json", lambda r: r["useCases"][0]["endpoints"].append("GET /nothing/here/{id}"))
        render.catalogs(self.out)
        ghost = next(e for e in out.load(self.out, "endpoints.json")["endpoints"] if e["path"] == "/nothing/here/{}")
        led = ledger.compute(self.out)
        self.assertEqual(led["classes"]["endpoints"]["total"], 3)
        self.assertNotIn("GET /nothing/here/{}", [u["item"] for u in led["classes"]["endpoints"]["uncovered"]])
        text = render.spec(self.out)
        self.assertRegex(text, r"### " + ghost["id"] + r" — GET /nothing/here/\{\} \(UNKNOWN \(open question OQ-\d{3}\)\)")
        self.assertRegex(text, r"- \*\*OQ-\d{3}:\*\* What are the contract \(.*not in the inventory.*\).*\(" + ghost["id"] + r"\)\?")

    def test_render_warnings_file_is_written_every_run(self):
        render.catalogs(self.out)
        self.assertEqual(out.load(self.out, "render-warnings.json"), [])
        self.edit("understand_result.json", lambda r: r["useCases"][0]["screens"].append("GhostScreen"))
        render.catalogs(self.out)
        self.assertEqual(out.load(self.out, "render-warnings.json"), [
            {"kind": "screen", "item": "GhostScreen",
             "why": "use case View payslip list names the screen GhostScreen, which understand_result.json does not have"}])

    def test_warning_unknown_use_case_in_a_screen(self):
        self.edit("understand_result.json", lambda r: r["screens"][1]["useCases"].append("Ghost"))
        self.assertEqual(self.warnings(), ["screen PayslipDetailView names the use case Ghost, which understand_result.json does not have"])

    def test_warning_duplicates_keep_the_first(self):
        def change(r):
            r["useCases"].append({**r["useCases"][0],
                                  "files": ["Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift"]})
            r["screens"].append(dict(r["screens"][0]))
            r["flows"].append(dict(r["flows"][0]))
        self.edit("understand_result.json", change)
        self.edit("rules_result.json", lambda r: r["rules"].append(dict(r["rules"][0])))
        warnings = self.warnings()
        self.assertIn("use case View payslip list appears twice; the first is kept", warnings)
        self.assertIn(f"screen PayslipListView appears twice in {LIST_VIEW}; the first is kept", warnings)
        self.assertIn("flow Read the latest payslip appears twice; the first is kept", warnings)
        self.assertTrue(any(w.startswith("rule Payslips are newest first appears twice in ") for w in warnings))
        self.assertEqual(len(warnings), 4)
        self.assertEqual(len(out.load(self.out, "use-cases.json")["useCases"]), 3)
        self.assertEqual(len(out.load(self.out, "rules.json")["rules"]), 2)

    def test_a_duplicate_use_case_does_not_overwrite_the_kept_files(self):
        render.catalogs(self.out)
        kept = out.load(self.out, "ids.json")["UCfiles"]["UC-001"]
        self.assertTrue(kept)
        self.edit("understand_result.json", lambda r: r["useCases"].append({**r["useCases"][0], "files": ["Other.swift"]}))
        render.catalogs(self.out)
        self.assertEqual(out.load(self.out, "ids.json")["UCfiles"]["UC-001"], kept)

    def test_warning_merge_into_an_unknown_id(self):
        write_overrides(self.out, {"merge": [{"into": "UC-099", "from": ["UC-002"]}]})
        self.assertEqual(self.warnings(), ["merge into UC-099 ignored: no such use case"])
        self.assertIn("UC-002", [u["id"] for u in out.load(self.out, "use-cases.json")["useCases"]])

    def test_merge_chain_points_every_reference_at_the_last_kept_id(self):
        write_overrides(self.out, {"merge": [{"into": "UC-002", "from": ["UC-003"]}, {"into": "UC-001", "from": ["UC-002"]}]})
        render.catalogs(self.out)
        cases = out.load(self.out, "use-cases.json")["useCases"]
        self.assertEqual([u["id"] for u in cases], ["UC-001"])
        self.assertEqual(sorted(cases[0]["screens"]), ["SCR-001", "SCR-002"])
        self.assertNotIn("UC-002", json.dumps(out.load(self.out, "flows.json")))
        self.assertNotIn("UC-003", json.dumps(out.load(self.out, "screens.json")))

    def test_cli_prints_warnings_on_stderr(self):
        self.edit("understand_result.json", lambda r: r["useCases"][0]["endpoints"].append("GET /nothing/here/{id}"))
        code, stdout, err = run_cli(["render.py", "catalogs", self.out], module=render)
        self.assertEqual(code, 0)
        self.assertEqual(err, "warning: use case View payslip list cites GET /nothing/here/{id}, which is not in the inventory; "
                              "kept as EP-003 with label UNKNOWN\n")
        self.assertEqual(stdout, "useCases 3, screens 2, flows 1, rules 2, endpoints 3, outOfScope 0\n")


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
