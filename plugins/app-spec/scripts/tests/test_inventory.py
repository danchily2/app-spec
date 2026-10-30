import json
import os
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out

import inventory

IOS = str(FIX / "ios-app")
ANDROID = str(FIX / "android-app")
RN = str(FIX / "rn-app")


def build_out(tmp, app, module_name, name):
    """Run module.py on a fixture app into `<tmp>/<name>` and return that output folder."""
    dest = os.path.join(tmp, name)
    code, _, err = run_cli(["module.py", app, "--module", module_name, "--out", dest])
    assert code == 0, err
    return dest


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.ios_out = build_out(cls.tmp, IOS, "Payslips", "ios")
        cls.inv = inventory.run(cls.ios_out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_inventory_is_scoped_to_module(self):
        inv = self.inv
        self.assertTrue(inv["endpoints"])
        self.assertTrue(all(e["file"].startswith(("Modules/PayslipsFeature", "EmployeeServices/Payslips", "Employee/StartPage"))
                            for e in inv["endpoints"] + inv["screens"]))
        self.assertNotIn("CalendarFeature", json.dumps(inv))

    def test_inventory_keeps_unresolved_path_template(self):
        e = next(x for x in self.inv["endpoints"] if x["type"] == "GetPayslipPdf")  # fixture builds its path from a runtime value
        self.assertIn("{}", e["path"])
        self.assertTrue(e["raw"])

    def test_inventory_drops_events_outside_the_module(self):
        self.assertEqual(self.inv["events"], [])  # PayslipEvent lives in Core/, outside core and touch points

    def test_inventory_files_and_shape(self):
        for name in ("inventory.json", "INVENTORY.md", "fields.json"):
            self.assertTrue(os.path.isfile(os.path.join(self.ios_out, name)), name)
        saved = out.load(self.ios_out, "inventory.json")
        for key in ("screens", "routes", "endpoints", "events", "strings", "storage", "platform", "counts", "rules"):
            self.assertIn(key, saved)
        self.assertEqual(saved["counts"]["endpoints"], 2)
        self.assertEqual(sorted(saved["strings"]["keys"]), ["payslip.latest", "payslip.list.title", "payslip.pdf"])
        self.assertEqual(set(saved["counts"]), set(saved["rules"]))

    def test_inventory_md_names_every_count_with_its_rule(self):
        with open(os.path.join(self.ios_out, "INVENTORY.md"), encoding="utf-8") as fh:
            text = fh.read()
        for key, rule in self.inv["rules"].items():
            self.assertIn(key, text)
            self.assertIn(rule, text)

    def test_inventory_fields_json_matches_module_files(self):
        data = out.load(self.ios_out, "fields.json")
        self.assertEqual(data["version"], 1)
        self.assertEqual({s["screen"] for s in data["screens"]}, {"PayslipListView", "PayslipDetailView", "PayslipCard"})

    def test_inventory_fills_shard_hints_from_the_files_of_each_shard(self):
        shards = [out.load(self.ios_out, e["file"]) for e in out.load(self.ios_out, "module.json")["shards"]]
        paths = sorted(p for s in shards for p in s["hints"]["endpoints"])
        self.assertEqual(paths, ["GET /employee/api/v1/employees/{}/payslips", "GET /employee/api/v1/{}"])
        for shard in shards:
            for e in self.inv["endpoints"]:
                inside = e["file"].rpartition(":")[0] in shard["files"]
                self.assertEqual(f"{e['method']} {e['path']}" in shard["hints"]["endpoints"], inside)

    def test_inventory_cli_prints_counts_with_rules_and_fields(self):
        code, stdout, _ = run_cli(["inventory.py", self.ios_out])
        self.assertEqual(code, 0)
        self.assertIn("endpoints", stdout)
        self.assertIn("rule:", stdout)
        self.assertIn("fields.json: 3 screens", stdout)

    def test_inventory_not_an_output_folder_exits_2(self):
        code, _, err = run_cli(["inventory.py", self.tmp])
        self.assertEqual(code, 2)
        self.assertIn("not an app-spec output folder", err)

    def test_inventory_android_and_rn(self):
        for app in (ANDROID, RN):
            dest = build_out(self.tmp, app, "payslips", os.path.basename(app))
            inv = inventory.run(dest)
            self.assertEqual(inv["endpoints"][0]["path"], "/employee/api/v1/employees/{}/payslips")
            self.assertIn("PayslipListScreen", [s["screen"] for s in out.load(dest, "fields.json")["screens"]])


if __name__ == "__main__":
    unittest.main()
