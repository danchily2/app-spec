import shutil
import tempfile
import unittest

from helpers import run_cli
from speclib import out
from test_render_catalogs import build_out, read_text, write_overrides

import ledger
import render

LIST_PATH = "GET /employee/api/v1/employees/{}/payslips"
PDF_PATH = "GET /employee/api/v1/{}"
CARD = "Employee/StartPage/PayslipCard.swift"


def edit(dest, name, change):
    """Load the catalog `name`, let `change` mutate it, save it."""
    data = out.load(dest, name)
    change(data)
    out.save(dest, name, data)


def uc(dest, ident):
    return next(u for u in out.load(dest, "use-cases.json")["useCases"] if u["id"] == ident)


def cover_everything(dest):
    """Edit the rendered catalogs of the ios fixture so that every inventory item is referenced: the touch-point screen
    gets a catalog entry with its elements, the PDF endpoint and the two unused string keys get a use case."""
    fields = out.load(dest, "fields.json")["screens"]
    card = next(s for s in fields if s["screen"] == "PayslipCard")

    def screens(data):
        data["screens"].append({"id": "SCR-004", "name": "PayslipCard", "file": card["file"], "useCases": ["UC-002"],
                                "actions": [], "states": [], "elements": [dict(e) for e in card["elements"]]})

    def cases(data):
        case = next(u for u in data["useCases"] if u["id"] == "UC-002")
        case["endpoints"] = ["EP-001"]
        case["strings"] = ["payslip.latest", "payslip.pdf"]

    def endpoints(data):
        next(e for e in data["endpoints"] if e["id"] == "EP-001")["useCases"] = ["UC-002"]

    edit(dest, "screens.json", screens)
    edit(dest, "use-cases.json", cases)
    edit(dest, "endpoints.json", endpoints)


LIST_VIEW = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift"


def card_in_core(dest):
    """Make the start-page card a core file, so its screen and fields count toward the thresholds."""
    edit(dest, "module.json", lambda m: m["core"].append(CARD))


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def base(self, name="base"):
        """The ios fixture as `render.py catalogs` leaves it: not every item is referenced."""
        dest = build_out(self.tmp, name)
        render.catalogs(dest)
        return dest

    def full(self, name="full"):
        dest = self.base(name)
        cover_everything(dest)
        return dest

    def missing_endpoint(self):
        dest = self.full("missing")
        edit(dest, "endpoints.json", lambda d: next(e for e in d["endpoints"] if e["id"] == "EP-002").update(useCases=[]))
        edit(dest, "use-cases.json", lambda d: next(u for u in d["useCases"] if u["id"] == "UC-001").update(endpoints=[]))
        return dest

    def thirty_strings(self, cited):
        """The full fixture with 30 module string keys, of which `cited` are cited by a use case."""
        dest = self.full("thirty")
        keys = [f"payslip.key{i:02d}" for i in range(30)]
        edit(dest, "module.json", lambda d: d.update(stringKeys=keys))
        edit(dest, "use-cases.json", lambda d: next(u for u in d["useCases"] if u["id"] == "UC-001").update(strings=keys[:cited]))
        edit(dest, "screens.json", lambda d: [e.update(textKey=None) for s in d["screens"] for e in s["elements"]])
        return dest


class TestBrief(LedgerCase):
    def test_all_covered_passes(self):
        self.assertTrue(ledger.compute(self.full())["pass"])

    def test_unreferenced_endpoint_fails_and_is_listed(self):
        led = ledger.compute(self.missing_endpoint())
        self.assertFalse(led["pass"])
        self.assertIn(LIST_PATH, [u["item"] for u in led["classes"]["endpoints"]["uncovered"]])

    def test_override_reason_makes_it_pass(self):
        dest = self.missing_endpoint()
        write_overrides(dest, {"drop": [{"kind": "endpoint", "id": "EP-002", "reason": "dead code"}]})
        led = ledger.compute(dest)
        self.assertTrue(led["pass"])
        self.assertEqual(led["classes"]["endpoints"]["uncovered"][0]["reason"], "dead code")

    def test_strings_threshold_95(self):
        led = ledger.compute(self.thirty_strings(29))  # 29 of 30 is 96.7 percent
        self.assertTrue(led["pass"])
        self.assertEqual(led["classes"]["strings"]["total"], 30)
        self.assertEqual([u["item"] for u in led["classes"]["strings"]["uncovered"]], ["payslip.key29"])


class TestRules(LedgerCase):
    def test_strings_below_the_threshold_fail(self):
        led = ledger.compute(self.thirty_strings(28))  # 93.3 percent
        self.assertFalse(led["pass"])
        self.assertFalse(led["classes"]["strings"]["pass"])

    def test_a_class_with_no_items_passes(self):
        led = ledger.compute(self.full())
        for name in ("events", "storage", "permissions"):
            cls = led["classes"][name]
            self.assertEqual((cls["total"], cls["covered"], cls["percent"], cls["pass"]), (0, 0, 100, True), name)

    def test_a_field_drop_counts_with_its_reason(self):
        dest = self.full()
        card_in_core(dest)
        edit(dest, "screens.json", lambda d: next(s for s in d["screens"] if s["id"] == "SCR-004")["elements"].pop())
        # the second PayslipCard element is gone from the catalog; 9 of 10 fields are covered, below 95 percent
        self.assertFalse(ledger.compute(dest)["pass"])
        write_overrides(dest, {"drop": [{"kind": "field", "id": "SCR-004.text-1", "reason": "decorative"}]})
        led = ledger.compute(dest)
        self.assertTrue(led["pass"])
        self.assertEqual(led["classes"]["fields"]["uncovered"], [{"item": "SCR-004.text-1", "reason": "decorative"}])
        self.assertEqual(led["classes"]["fields"]["covered"], 10)

    def test_a_dropped_field_leaves_the_covered_count_but_not_the_total(self):
        dest = self.full()
        write_overrides(dest, {"drop": [{"kind": "field", "id": "SCR-001.refresh", "reason": "removed in the new app"}]})
        cls = ledger.compute(dest)["classes"]["fields"]
        self.assertEqual(cls["total"], 10)
        self.assertEqual(cls["uncovered"], [{"item": "SCR-001.refresh", "reason": "removed in the new app"}])
        self.assertEqual(cls["withReason"], 1)

    def test_a_drop_without_a_reason_does_not_count(self):
        dest = self.missing_endpoint()
        write_overrides(dest, {"drop": [{"kind": "endpoint", "id": "EP-002", "reason": "  "}]})
        led = ledger.compute(dest)
        self.assertFalse(led["pass"])
        self.assertIsNone(led["classes"]["endpoints"]["uncovered"][0]["reason"])

    def test_a_dropped_screen_takes_its_fields_with_it(self):
        dest = self.full()
        card_in_core(dest)
        write_overrides(dest, {"drop": [{"kind": "screen", "id": "SCR-004", "reason": "out of module"}]})
        led = ledger.compute(dest)
        self.assertTrue(led["pass"])
        self.assertEqual([u["reason"] for u in led["classes"]["screens"]["uncovered"]], ["out of module"])
        self.assertEqual({u["reason"] for u in led["classes"]["fields"]["uncovered"]}, {"out of module"})

    def test_a_dropped_use_case_uncovers_what_only_it_referenced(self):
        dest = self.full()
        write_overrides(dest, {"drop": [{"kind": "useCase", "id": "UC-002", "reason": "not in scope"}]})
        led = ledger.compute(dest)
        self.assertFalse(led["pass"])
        self.assertIn(PDF_PATH, [u["item"] for u in led["classes"]["endpoints"]["uncovered"]])

    def test_a_dropped_string_and_event_are_read_through_the_spec_keys(self):
        dest = self.base()
        write_overrides(dest, {"drop": [{"kind": "string", "id": "payslip.pdf", "reason": "dead code"}]})
        unc = ledger.compute(dest)["classes"]["strings"]["uncovered"]
        self.assertIn({"item": "payslip.pdf", "reason": "dead code"}, unc)

    def test_events_storage_and_permissions_are_matched_by_name(self):
        dest = self.full()
        edit(dest, "inventory.json", lambda d: d.update(
            events=[{"name": "payslip_opened", "file": f"{LIST_VIEW}:1"}, {"name": "payslip_shared", "file": f"{LIST_VIEW}:2"}],
            storage=[{"kind": "userdefaults", "key": "lastPayslipId", "file": f"{LIST_VIEW}:3"}]))
        edit(dest, "inventory.json", lambda d: d["platform"].update(
            permissions=[{"key": "NSCameraUsageDescription", "file": f"{LIST_VIEW}:4"}]))
        edit(dest, "use-cases.json", lambda d: next(u for u in d["useCases"] if u["id"] == "UC-001").update(
            events=["payslip_opened"], storage=["lastPayslipId"]))
        led = ledger.compute(dest)["classes"]
        self.assertEqual([u["item"] for u in led["events"]["uncovered"]], ["payslip_shared"])
        self.assertEqual((led["events"]["total"], led["events"]["covered"]), (2, 1))
        self.assertEqual((led["storage"]["total"], led["storage"]["covered"]), (1, 1))
        self.assertEqual([u["item"] for u in led["permissions"]["uncovered"]], ["NSCameraUsageDescription"])

    def test_dropped_storage_and_permission_leave_the_spec_and_count_with_their_reason(self):
        dest = self.full()
        edit(dest, "inventory.json", lambda d: d.update(storage=[{"kind": "userdefaults", "key": "lastPayslipId",
                                                                  "file": f"{LIST_VIEW}:3"}]))
        edit(dest, "inventory.json", lambda d: d["platform"].update(
            permissions=[{"key": "NSCameraUsageDescription", "file": f"{LIST_VIEW}:4"}], urlSchemes=["vismapay"]))
        before = render.spec(dest)
        self.assertIn("lastPayslipId", before)
        self.assertIn("NSCameraUsageDescription", before)
        write_overrides(dest, {"drop": [
            {"kind": "storage", "id": "lastPayslipId", "reason": "dead code"},
            {"kind": "permission", "id": "NSCameraUsageDescription", "reason": "out of module"},
            {"kind": "platform", "id": "urlSchemes:vismapay", "reason": "not user-facing"}]})
        led = ledger.compute(dest)
        self.assertTrue(led["pass"])
        self.assertEqual(led["classes"]["storage"]["uncovered"], [{"item": "lastPayslipId", "reason": "dead code"}])
        self.assertEqual(led["classes"]["permissions"]["uncovered"],
                         [{"item": "NSCameraUsageDescription", "reason": "out of module"}])
        self.assertEqual(led["classes"]["platform"]["uncovered"], [{"item": "urlSchemes:vismapay", "reason": "not user-facing"}])
        text = render.spec(dest)
        appendix_d = text.split("## Appendix D.")[1].split("## Appendix E.")[0]
        appendix_f = text.split("## Appendix F.")[1]
        for item in ("lastPayslipId", "NSCameraUsageDescription", "vismapay"):
            self.assertNotIn(item, appendix_d)
            self.assertIn(item, appendix_f)
        self.assertIn("| storage | lastPayslipId | dead code |", appendix_f)

    def test_thresholds_come_from_the_configuration(self):
        dest = self.base()
        self.assertEqual(ledger.compute(dest)["thresholds"]["strings"], 95)
        cfg = out.load_config(dest)
        cfg["options"]["thresholds"]["strings"] = 30
        out.save(dest, "app-spec.json", cfg)
        led = ledger.compute(dest)
        self.assertEqual(led["thresholds"]["strings"], 30)
        self.assertTrue(led["classes"]["strings"]["pass"])  # 1 of 3 is 33.3 percent


class TestClasses(LedgerCase):
    """One assertion per class on the ios fixture as the catalogs render it."""

    def setUp(self):
        super().setUp()
        self.led = ledger.compute(self.base())["classes"]

    def test_screens(self):
        cls = self.led["screens"]
        self.assertEqual((cls["total"], cls["covered"]), (2, 2))  # the touch-file card is not the module's own
        self.assertEqual(cls["uncovered"], [])
        self.assertEqual(cls["informational"], [f"{CARD}:3 PayslipCard"])

    def test_fields(self):
        cls = self.led["fields"]
        self.assertEqual((cls["total"], cls["covered"]), (8, 8))
        self.assertEqual(cls["informational"], [f"{CARD}.payslip-latest", f"{CARD}.text-1"])

    def test_endpoints(self):
        cls = self.led["endpoints"]
        self.assertEqual((cls["total"], cls["covered"]), (2, 1))
        self.assertEqual([u["item"] for u in cls["uncovered"]], [PDF_PATH])

    def test_strings(self):
        cls = self.led["strings"]
        self.assertEqual((cls["total"], cls["covered"]), (3, 1))
        self.assertEqual([u["item"] for u in cls["uncovered"]], ["payslip.latest", "payslip.pdf"])

    def test_events(self):
        self.assertEqual((self.led["events"]["total"], self.led["events"]["covered"]), (0, 0))

    def test_storage(self):
        self.assertEqual((self.led["storage"]["total"], self.led["storage"]["covered"]), (0, 0))

    def test_permissions(self):
        self.assertEqual((self.led["permissions"]["total"], self.led["permissions"]["covered"]), (0, 0))

    def test_platform(self):
        self.assertEqual((self.led["platform"]["total"], self.led["platform"]["covered"]), (0, 0))

    def test_all_eight_classes_are_present(self):
        self.assertEqual(sorted(self.led), ["endpoints", "events", "fields", "permissions", "platform", "screens",
                                            "storage", "strings"])


class TestFiles(LedgerCase):
    def test_compute_writes_the_ledger_and_its_view(self):
        dest = self.base()
        led = ledger.compute(dest)
        self.assertEqual(out.load(dest, "ledger.json"), led)
        self.assertEqual(led["version"], 1)
        text = read_text(dest, "LEDGER.md")
        self.assertIn("| endpoints | 2 | 1 | 0 | 1 | 50 | 100 | fail |", text)
        self.assertIn(f"- `{PDF_PATH}`: no reason", text)

    def test_the_view_lists_the_reason_of_an_uncovered_item(self):
        dest = self.missing_endpoint()
        write_overrides(dest, {"drop": [{"kind": "endpoint", "id": "EP-002", "reason": "dead code"}]})
        ledger.compute(dest)
        text = read_text(dest, "LEDGER.md")
        self.assertIn(f"- `{LIST_PATH}`: dead code", text)
        self.assertIn("Result: pass", text)

    def test_a_run_is_deterministic(self):
        dest = self.base()
        ledger.compute(dest)
        first = (read_text(dest, "ledger.json"), read_text(dest, "LEDGER.md"))
        ledger.compute(dest)
        self.assertEqual(first, (read_text(dest, "ledger.json"), read_text(dest, "LEDGER.md")))

    def test_the_spec_appendix_reads_the_ledger(self):
        dest = self.full()
        ledger.compute(dest)
        text = render.spec(dest)
        self.assertIn("Result: pass", text)

    def test_cli_exits_1_on_fail_and_0_on_pass(self):
        code, stdout, _ = run_cli(["ledger.py", self.base()])
        self.assertEqual(code, 1)
        self.assertIn("fail", stdout)
        code, stdout, _ = run_cli(["ledger.py", self.full()])
        self.assertEqual(code, 0)
        self.assertIn("pass", stdout)

    def test_cli_exits_2_for_a_folder_that_is_not_an_output_folder(self):
        code, _, err = run_cli(["ledger.py", self.tmp])
        self.assertEqual(code, 2)
        self.assertIn("not an app-spec output folder", err)
        self.assertEqual(run_cli(["ledger.py"])[0], 2)

    def test_a_missing_catalog_exits_2(self):
        dest = build_out(self.tmp, "nocatalogs")
        code, _, err = run_cli(["ledger.py", dest])
        self.assertEqual(code, 2)
        self.assertIn("use-cases.json", err)


if __name__ == "__main__":
    unittest.main()


class TestCoreOnly(LedgerCase):
    """Thresholds hold the module's own items; touch-only items are listed apart."""

    def test_inventory_marks_each_entry_core_or_touch(self):
        dest = self.base()
        inv = out.load(dest, "inventory.json")
        scopes = {e["name"]: e["scope"] for e in inv["screens"] + inv.get("swiftuiViews", [])}
        self.assertEqual(scopes["PayslipCard"], "touch")
        self.assertEqual(scopes["PayslipListView"], "core")
        self.assertEqual({s["screen"]: s["scope"] for s in out.load(dest, "fields.json")["screens"]}["PayslipCard"], "touch")

    def test_a_touch_item_a_use_case_cites_counts(self):
        dest = self.base()
        edit(dest, "inventory.json", lambda d: d.update(events=[{"name": "card_seen", "file": f"{CARD}:4", "scope": "touch"},
                                                              {"name": "card_hidden", "file": f"{CARD}:5", "scope": "touch"}]))
        edit(dest, "use-cases.json", lambda d: d["useCases"][0].update(events=["card_seen"]))
        cls = ledger.compute(dest)["classes"]["events"]
        self.assertEqual((cls["total"], cls["covered"], cls["informational"]), (1, 1, ["card_hidden"]))

    def test_a_reducer_beside_a_kept_screen_is_covered(self):
        dest = self.base()
        folder = "Modules/PayslipsFeature/Sources/PayslipsFeature"
        edit(dest, "inventory.json", lambda d: d["screens"].extend([
            {"name": "PayslipListFeature", "kind": "tca-feature", "file": f"{folder}/PayslipListFeature.swift:5", "scope": "core"},
            {"name": "Destination", "kind": "tca-feature", "file": f"{folder}/PayslipListFeature.swift:20", "scope": "core"},
            {"name": "OrphanFeature", "kind": "tca-feature", "file": "Modules/Other/Sources/Other/Orphan.swift:3", "scope": "core"}]))
        edit(dest, "module.json", lambda m: m["core"].append("Modules/Other/Sources/Other/Orphan.swift"))
        cls = ledger.compute(dest)["classes"]["screens"]
        self.assertEqual([u["item"] for u in cls["uncovered"]], ["Modules/Other/Sources/Other/Orphan.swift:3 OrphanFeature"])
        self.assertEqual((cls["total"], cls["covered"]), (5, 4))

    def test_ledger_md_lists_touch_only_items_apart(self):
        dest = self.base()
        ledger.compute(dest)
        text = read_text(dest, "LEDGER.md")
        apart = text.split("## Outside the module (not counted)")[1]
        self.assertIn(f"`{CARD}:3 PayslipCard`", apart)
        self.assertNotIn("PayslipCard", text.split("## Outside the module (not counted)")[0])
