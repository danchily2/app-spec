import contextlib
import io
import shutil
import tempfile
import unittest

from helpers import FIX
from speclib import detect, ios, out


class TestSpeclib(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_detect_fixture_stacks(self):
        self.assertEqual(detect.detect(FIX / "ios-app")["stack"], "ios-native")
        self.assertEqual(detect.detect(FIX / "android-app")["stack"], "android-native")
        self.assertEqual(detect.detect(FIX / "rn-app")["stack"], "react-native")

    def test_ios_extract_resolves_endpoint_constant(self):
        inv = ios.extract(str(FIX / "ios-app"))
        pairs = {(e["method"], e["path"]) for e in inv["endpoints"]}
        self.assertIn(("GET", "/employee/api/v1/employees/{}/payslips"), pairs)

    def test_ios_reducer_without_a_store_is_not_a_screen(self):
        root = self.tmp + "/tca-app"
        import os
        os.makedirs(root + "/Feature")
        with open(root + "/Feature/Main.swift", "w") as f:
            f.write("@Reducer\nstruct MainFeature {}\n@Reducer\nstruct AnalyticsFeature {}\n"
                    "@Reducer\nstruct DetailFeature {}\n"
                    "struct MainView: View {\n  let store: StoreOf<MainFeature>\n  var body: some View { Text(\"x\") }\n}\n"
                    "struct DetailView: View {\n  let store: Store<DetailFeature.State, DetailFeature.Action>\n"
                    "  var body: some View { Text(\"y\") }\n}\n")
        inv = ios.extract(root)
        screens = {s["name"] for s in inv["screens"] if s["kind"] == "tca-feature"}
        self.assertEqual(screens, {"MainFeature", "DetailFeature"})
        self.assertEqual([r["name"] for r in inv["tcaReducers"]], ["AnalyticsFeature"])
        self.assertEqual(inv["tcaReducers"][0]["kind"], "tca-reducer")
        self.assertEqual(inv["counts"]["tcaReducers"], 1)

    def test_out_roundtrip(self):
        path = out.save(self.tmp, "x.json", {"a": 1})
        self.assertEqual(out.load(self.tmp, "x.json"), {"a": 1})
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{\n  "a": 1\n}\n')

    def test_load_config_missing_exits(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            out.load_config(self.tmp)
        self.assertIn("not an app-spec output folder", err.getvalue())
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
