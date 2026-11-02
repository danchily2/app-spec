import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import FIX, run_cli
from speclib import out, touchpoints

import module

IOS = str(FIX / "ios-app")
INDEX = str(FIX / "capability_index.json")


def catalog(app):
    return module.load_catalog(app, "ios-native")


def core_files(app):
    """Absolute paths of the files of the Payslips module in the iOS fixture."""
    core = module.resolve_by_name(app, "ios-native", ["Payslips"])["core"]
    return [os.path.join(app, f) for f in module.files_under(app, "ios-native", core)]


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestModule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_resolve_payslips_core_folders(self):
        r = module.resolve_by_name(IOS, "ios-native", ["Payslips"])
        self.assertEqual(sorted(r["core"]), ["EmployeeServices/Payslips", "Modules/PayslipsFeature"])

    def test_resolve_unknown_name_has_no_core(self):
        self.assertEqual(module.resolve_by_name(IOS, "ios-native", ["Nothing"])["core"], [])

    def test_touch_point_start_page_card(self):
        tps = touchpoints.find(IOS, "ios-native", core_files(IOS), ["payslip.latest"])
        self.assertIn({"file": "Employee/StartPage/PayslipCard.swift", "reason": "uses type PayslipItem"}, tps)

    def test_string_keys_for_core(self):
        self.assertEqual(sorted(module.string_keys_for(core_files(IOS), catalog(IOS))),
                         ["payslip.latest", "payslip.list.title", "payslip.pdf"])

    def test_string_keys_through_a_generated_accessor_type(self):
        # P6: me-ios uses S.Payslips.payslipTitle (Strings.swift: static let payslipTitle = "PAYSLIP_TITLE"); the run
        # found 0 of the payslip strings because only quoted literals in core files were read
        app = os.path.join(self.tmp, "accessors")
        write(app, "Resources/Strings.swift",
              'public struct S {\n    public static let ok = "OK"\n    public struct Payslips {\n'
              '        public static let payslipTitle = "PAYSLIP_TITLE"\n        public static let unused = "X_UNUSED"\n'
              '        public struct Export { public static let button = "EXPORT_BUTTON" }\n    }\n'
              '    public static let notAKey = "not in the catalog"\n}\n')
        write(app, "Feature/PayslipView.swift",
              'struct PayslipView: View {\n    var body: some View {\n'
              '        Text(S.Payslips.payslipTitle.localized)\n        Button(S.ok.localized) {}\n'
              '        Text(S.Payslips.Export.button.localized)\n    }\n}\n')
        catalog = {"keys": {"OK": {}, "PAYSLIP_TITLE": {}, "X_UNUSED": {}, "EXPORT_BUTTON": {}}}
        self.assertEqual(module.string_keys_for(["Feature/PayslipView.swift"], catalog, app),
                         ["EXPORT_BUTTON", "OK", "PAYSLIP_TITLE"])

    def test_small_parts_merge_only_within_one_top_folder(self):
        # P5/P12: shards such as [EmployeeServices/Payslips..Modules/EmployeeAppCore] mixed unrelated packages
        parts = [("EmployeeServices/Payslips", {"a.swift": 50}), ("EmployeeServices/PayslipsInterface", {"b.swift": 40}),
                 ("Modules/EmployeeAppCore", {"c.swift": 30}), ("Modules/RemoteControl", {"d.swift": 20}),
                 ("Employee", {"e.swift": 900})]
        packed = module._pack(parts, 2000)
        names = sorted(name for name, _ in packed)
        self.assertEqual(names, ["Employee", "EmployeeServices/{Payslips, PayslipsInterface}",
                                 "Modules/{EmployeeAppCore, RemoteControl}"])
        self.assertEqual(sorted(f for _, files in packed for f in files), ["a.swift", "b.swift", "c.swift", "d.swift", "e.swift"])
        self.assertEqual(module._pack_name(["Modules", "Modules/EmployeeAppCore"]), "Modules/{., EmployeeAppCore}")

    def test_shards_respect_max_lines_and_lose_no_file(self):
        app = os.path.join(self.tmp, "big")
        big_file_list = []
        for folder in ("a", "b", "c/one", "c/two"):
            for i in range(5):
                rel = f"{folder}/File{i}.swift"
                write(app, rel, "\n".join(f"let v{n} = {n}" for n in range(25)) + "\n\n")
                big_file_list.append(rel)
        shards = module.make_shards(app, big_file_list, "core", max_lines=120)
        self.assertGreater(len(shards), 1)
        self.assertTrue(all(s["loc"] <= 120 for s in shards))
        self.assertEqual(sorted(f for s in shards for f in s["files"]), sorted(big_file_list))
        self.assertEqual(len({s["id"] for s in shards}), len(shards))
        self.assertTrue(all(s["id"].startswith("core-") and s["kind"] == "core" for s in shards))

    def test_cli_writes_config_and_module(self):
        rc, stdout, _ = run_cli(["module.py", IOS, "--module", "Payslips", "--out", self.tmp])
        self.assertEqual(rc, 0)
        cfg = out.load_config(self.tmp)
        self.assertFalse(cfg["module"]["confirmed"])
        self.assertEqual(cfg["app"]["stack"], "ios-native")
        self.assertTrue((Path(self.tmp) / "module.json").exists())
        self.assertIn("EmployeeServices/Payslips", stdout)

    def test_cli_refuses_out_inside_a_contract_repository(self):
        backend = os.path.join(self.tmp, "backend")
        os.makedirs(os.path.join(backend, "src"))
        dest = os.path.join(backend, "specs", "payslips")
        rc, _, err = run_cli(["module.py", IOS, "--module", "Payslips", "--out", dest, "--contracts", backend])
        self.assertEqual(rc, 2)
        self.assertIn("inside the contract repository", err)
        self.assertFalse(os.path.exists(dest), "nothing is written into the contract repository")
        rc, _, _ = run_cli(["module.py", IOS, "--module", "Payslips", "--out", backend, "--contracts", backend])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(os.path.join(backend, "app-spec.json")))

    def test_cli_refuses_a_contract_repository_inside_out(self):
        dest = os.path.join(self.tmp, "o")
        backend = os.path.join(dest, "backend")
        os.makedirs(backend)
        rc, _, err = run_cli(["module.py", IOS, "--module", "Payslips", "--out", dest, "--contracts", backend])
        self.assertEqual(rc, 2)
        self.assertIn("inside --out", err)
        self.assertFalse(os.path.exists(os.path.join(dest, "app-spec.json")))

    def test_cli_ambiguous_name_exits_2(self):
        rc, _, err = run_cli(["module.py", IOS, "--module", "Feature", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn("several folders match Feature: Modules/CalendarFeature, Modules/PayslipsFeature", err)
        self.assertFalse((Path(self.tmp) / "app-spec.json").exists())

    def test_scope_from_index_unions_files(self):
        files = module.scope_from_index(INDEX, ["CAP-001", "CAP-002"], "ios-app")
        self.assertEqual(files, ["Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift",
                                 "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift"])

    def test_scope_unknown_capability_exits(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            module.scope_from_index(INDEX, ["CAP-999"], "ios-app")

    def test_cli_scope_records_index(self):
        rc, _, _ = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-001", "--out", self.tmp])
        self.assertEqual(rc, 0)
        cfg = out.load_config(self.tmp)
        self.assertEqual(cfg["scope"], ["CAP-001"])
        self.assertEqual(cfg["capabilityIndex"], os.path.realpath(INDEX))
        mod = out.load(self.tmp, "module.json")
        self.assertEqual(mod["core"], ["Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift"])

    def test_cli_module_with_scope_adds_the_folders_to_the_capability_files(self):
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-001",
                              "--module", "EmployeeServices/Payslips", "--out", self.tmp])
        self.assertEqual(rc, 0, err)
        core = json.load(open(os.path.join(self.tmp, "module.json")))["core"]
        self.assertIn("Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift", core)
        self.assertIn("EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift", core)

    def test_cli_scope_with_no_ids_exits_2(self):
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", ",", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn("--scope has no capability ids", err)
        self.assertFalse((Path(self.tmp) / "app-spec.json").exists())

    def test_cli_scope_file_missing_on_disk_exits_2(self):
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-004", "--out", self.tmp])
        self.assertEqual(rc, 2)
        missing = os.path.join(os.path.realpath(IOS), "Modules/PayslipsFeature/Sources/PayslipsFeature/RemovedView.swift")
        self.assertIn(f"index file not found: {missing}", err)
        self.assertFalse((Path(self.tmp) / "app-spec.json").exists())

    def test_scope_exit_messages(self):
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-999", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn("unknown capability CAP-999", err)
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", INDEX, "--scope", "CAP-003", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn("app ios-app has no implementation of CAP-003", err)
        write(self.tmp, "capability_index.json", json.dumps({"capabilities": [{"id": "CAP-001", "name": "x"}]}))
        compact = os.path.realpath(os.path.join(self.tmp, "capability_index.json"))
        rc, _, err = run_cli(["module.py", IOS, "--capabilities", compact, "--scope", "CAP-001", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn(f"no implementations in {compact}: pass capabilities.json", err)

    # ---- beyond the brief's seven

    def test_cli_unknown_name_exits_2(self):
        rc, _, err = run_cli(["module.py", IOS, "--module", "Nothing", "--out", self.tmp])
        self.assertEqual(rc, 2)
        self.assertIn("no folder matches Nothing", err)

    def test_cli_path_disambiguates_and_files_are_consistent(self):
        rc, _, _ = run_cli(["module.py", IOS, "--module", "Modules/CalendarFeature", "--out", self.tmp,
                            "--confirmed", "--locale", "da", "--max-lines", "50"])
        self.assertEqual(rc, 0)
        cfg = out.load_config(self.tmp)
        self.assertTrue(cfg["module"]["confirmed"])
        self.assertEqual(cfg["module"]["query"], ["Modules/CalendarFeature"])
        self.assertEqual(cfg["options"]["locale"], "da")
        self.assertEqual(cfg["options"]["passes"], 2)
        self.assertEqual(cfg["options"]["thresholds"]["strings"], 95)
        self.assertEqual(cfg["contracts"], [])
        mod = out.load(self.tmp, "module.json")
        self.assertEqual(mod["core"], ["Modules/CalendarFeature/Sources/CalendarFeature/CalendarView.swift"])
        self.assertEqual(mod["stringKeys"], ["calendar.title"])
        self.assertEqual(mod["loc"], sum(s["loc"] for s in mod["shards"]))
        for entry in mod["shards"]:
            shard = out.load(self.tmp, entry["file"])
            self.assertEqual(shard["files"], entry["files"])
            self.assertEqual(shard["hints"], {"routes": [], "screens": [], "endpoints": [], "events": []})
            self.assertNotIn("file", shard)

    def test_cli_rerun_updates_owned_fields_and_keeps_the_rest(self):
        run_cli(["module.py", IOS, "--module", "Payslips", "--out", self.tmp])
        cfg = out.load_config(self.tmp)
        cfg["options"]["passes"] = 4
        cfg["extra"] = "added by a person"
        out.save(self.tmp, "app-spec.json", cfg)
        rc, _, _ = run_cli(["module.py", IOS, "--module", "Modules/CalendarFeature", "--out", self.tmp, "--confirmed"])
        self.assertEqual(rc, 0)
        again = out.load_config(self.tmp)
        self.assertTrue(again["module"]["confirmed"])
        self.assertEqual(again["module"]["query"], ["Modules/CalendarFeature"])
        self.assertEqual(again["options"]["passes"], 4)
        self.assertEqual(again["options"]["locale"], "en")
        self.assertEqual(again["extra"], "added by a person")
        self.assertEqual(again["created"], cfg["created"])
        run_cli(["module.py", IOS, "--module", "Modules/CalendarFeature", "--out", self.tmp, "--locale", "sv"])
        last = out.load_config(self.tmp)
        self.assertTrue(last["module"]["confirmed"])  # not passing --confirmed leaves the stored value
        self.assertEqual(last["options"]["locale"], "sv")

    def test_rn_exported_constant_creates_no_touch_point(self):
        app = os.path.join(self.tmp, "rn")
        shutil.copytree(FIX / "rn-app", app)
        with open(os.path.join(app, "src/payslips/PayslipListScreen.tsx"), "a", encoding="utf-8") as fh:
            fh.write("\nexport const styles = {};\nexport const config = {};\nexport const usePayslipCount = () => 1;\n")
        write(app, "src/other/Other.tsx", "import { styles, config } from './x';\nexport const Other = () => styles && config;\n")
        write(app, "src/other/Count.tsx", "const n = usePayslipCount();\n")
        core = ["src/payslips/PayslipListScreen.tsx"]
        tps = touchpoints.find(app, "react-native", core, [])
        self.assertEqual(tps, [{"file": "src/other/Count.tsx", "reason": "uses type usePayslipCount"}])

    def test_touch_point_reasons_in_order(self):
        app = os.path.join(self.tmp, "app")
        write(app, "Modules/Orders/Sources/Orders/Orders.swift",
              "struct GetOrders: APIClientRequest {}\nstruct OrderListView: View {}\nenum OrderEvent { case seen }\n"
              "struct OrderRow { let title = \"order.row\" }\n")
        write(app, "App/Client.swift", "let call = GetOrders()\n")
        write(app, "App/Nav.swift", "NavigationLink(destination: OrderListView()) { Text(\"go\") }\n")
        write(app, "App/Track.swift", "track(OrderEvent.seen)\n")
        write(app, "App/Label.swift", "let t = \"order.title\"\n")
        write(app, "App/Both.swift", "let r = OrderRow()\nlet t = \"order.title\"\nlet c = GetOrders()\n")
        write(app, "App/Unrelated.swift", "let x = 1\n")
        tps = touchpoints.find(app, "ios-native", ["Modules/Orders/Sources/Orders/Orders.swift"], ["order.title"])
        self.assertEqual(sorted((t["file"], t["reason"]) for t in tps), [
            ("App/Both.swift", "uses type OrderRow"),
            ("App/Client.swift", "uses request GetOrders"),
            ("App/Label.swift", "uses string key order.title"),
            ("App/Nav.swift", "routes into OrderListView"),
            ("App/Track.swift", "fires event family OrderEvent"),
        ])

    def test_nested_generic_types_do_not_make_another_feature_a_touch_point(self):
        app = os.path.join(self.tmp, "tca")
        write(app, "Modules/PayslipsFeature/Sources/PayslipsFeature/MainPayslipFeature.swift",
              "@Reducer\nstruct MainPayslipFeature {\n  struct ViewModel { let title: String }\n"
              "  enum Delegate { case done }\n  enum Destination { case pdf }\n"
              "  func track() { EmployeeAnalytics.log(.payslipOpened) }\n}\n")
        write(app, "Modules/ExpensesFeature/Sources/ExpensesFeature/ExpensesFeature.swift",
              "@Reducer\nstruct ExpensesFeature {\n  struct ViewModel { let total: Int }\n"
              "  enum Delegate { case saved }\n  func track() { EmployeeAnalytics.log(.expenseSaved) }\n}\n")
        write(app, "Employee/Analytics/EmployeeAnalytics.swift", "enum EmployeeAnalytics { case payslipOpened }\n")
        write(app, "Employee/Root/RootFeature.swift",
              "let dest: MainPayslipFeature.Destination = .pdf\nlet other = Other.MainPayslipFeature.Delegate.x\n")
        core = ["Modules/PayslipsFeature/Sources/PayslipsFeature/MainPayslipFeature.swift"]
        tps = touchpoints.find(app, "ios-native", core, [])
        self.assertEqual(tps, [{"file": "Employee/Root/RootFeature.swift",
                                "reason": "uses type MainPayslipFeature.Destination"}])

    def test_a_name_declared_outside_the_core_too_is_not_matched(self):
        app = os.path.join(self.tmp, "dup")
        write(app, "Modules/Payslips/Sources/Payslips/Loadable.swift", "enum Loadable {}\nstruct PayslipRow {}\n")
        write(app, "Modules/Shared/Sources/Shared/Loadable.swift", "public enum Loadable {}\n")
        write(app, "Modules/Calendar/Sources/Calendar/Grid.swift", "var days: Loadable = .idle\n")
        write(app, "App/Card.swift", "let row = PayslipRow()\nvar l: Loadable\n")
        tps = touchpoints.find(app, "ios-native", ["Modules/Payslips/Sources/Payslips/Loadable.swift"], [])
        self.assertEqual(tps, [{"file": "App/Card.swift", "reason": "uses type PayslipRow"}])

    def test_generic_top_level_names_are_not_matched(self):
        found = touchpoints.declared("ios-native", "struct Coordinator {}\nstruct Mapper {}\nstruct PayslipMapper {}\n")
        self.assertEqual(found["types"], {"PayslipMapper"})

    def test_cli_touch_keyword_filters_and_is_recorded(self):
        app = os.path.join(self.tmp, "kw")
        write(app, "Package.swift", "// swift-tools-version:5.9\n")
        write(app, "Modules/Orders/Sources/Orders/Orders.swift", "struct OrderRow {}\n")
        write(app, "App/OrderCard.swift", "let r = OrderRow() // order card\n")
        write(app, "App/Basket.swift", "let r = OrderRow()\n")
        dest = os.path.join(self.tmp, "out")
        code, stdout, _ = run_cli(["module.py", app, "--module", "Modules/Orders", "--out", dest,
                                   "--touch-keyword", "card"])
        self.assertEqual(code, 0)
        data = json.loads(Path(dest, "module.json").read_text())
        self.assertEqual([t["file"] for t in data["touchPoints"]], ["App/OrderCard.swift"])
        self.assertEqual(data["touchFilter"], {"keyword": "card", "dropped": 1})
        self.assertIn("Touch points: 1 (only those that contain 'card'; 1 dropped)", stdout)

    def test_a_rerun_with_other_modules_leaves_only_its_own_shards(self):
        dest = os.path.join(self.tmp, "out")
        run_cli(["module.py", IOS, "--module", "Payslips", "--out", dest])
        first = set(os.listdir(os.path.join(dest, "shards")))
        code, _, err = run_cli(["module.py", IOS, "--module", "Modules/CalendarFeature", "--out", dest])
        self.assertEqual(code, 0, err)
        second = {e["file"].split("/", 1)[1] for e in json.loads(Path(dest, "module.json").read_text())["shards"]}
        self.assertEqual(set(os.listdir(os.path.join(dest, "shards"))), second)
        self.assertTrue(first - second, "the first run had shards the second does not")
        Path(dest, "shards", "notes.txt").write_text("kept")
        run_cli(["module.py", IOS, "--module", "Modules/CalendarFeature", "--out", dest])
        self.assertTrue(Path(dest, "shards", "notes.txt").is_file(), "only shards/*.json are removed")

    def test_a_source_file_or_file_glob_joins_the_core(self):
        dest = os.path.join(self.tmp, "file")
        card = "Employee/StartPage/PayslipCard.swift"
        code, stdout, err = run_cli(["module.py", IOS, "--module", "Modules/PayslipsFeature", "--module", card,
                                     "--out", dest])
        self.assertEqual(code, 0, err)
        data = json.loads(Path(dest, "module.json").read_text())
        self.assertIn(card, data["core"])
        self.assertNotIn(card, [t["file"] for t in data["touchPoints"]])
        self.assertIn(f"Core files:\n  {card}", stdout)
        code, _, err = run_cli(["module.py", IOS, "--module", "EmployeeServices/Payslips/Sources/Payslips/Get*.swift",
                                "--out", os.path.join(self.tmp, "glob")])
        self.assertEqual(code, 0, err)
        core = json.loads(Path(self.tmp, "glob", "module.json").read_text())["core"]
        self.assertEqual(core, ["EmployeeServices/Payslips/Sources/Payslips/GetPayslipPdf.swift",
                                "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift"])

    def test_a_file_that_is_not_a_source_file_matches_nothing(self):
        code, _, err = run_cli(["module.py", IOS, "--module", "Resources/Localizable.xcstrings",
                                "--out", os.path.join(self.tmp, "none")])
        self.assertEqual(code, 2)
        self.assertIn("no folder or source file matches", err)


if __name__ == "__main__":
    unittest.main()
