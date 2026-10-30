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


if __name__ == "__main__":
    unittest.main()
