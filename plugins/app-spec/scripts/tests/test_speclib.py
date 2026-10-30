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
