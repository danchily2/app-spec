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

    def test_ios_url_built_by_concatenation_in_a_service_is_an_endpoint(self):
        # P11/P21: PayslipService.swift:155-156 builds allpayslips from two literals joined with +
        import os
        root = self.tmp + "/svc-app"
        os.makedirs(root + "/Service")
        with open(root + "/Service/PayslipService.swift", "w") as f:
            f.write('final class PayslipService {\n'
                    '    public func payslipUrl(odpUserId: Int, offset: Int) -> String {\n'
                    '        let payslipUrl = "\\(APIConstants.MEAPIBaseUrl.baseUrl)\\(APIConstants.URL.employeeApiV1)" +\n'
                    '                         "/employees/\\(odpUserId)/allpayslips?From=\\(date)&Offset=\\(offset)"\n'
                    '        return payslipUrl\n'
                    '    }\n'
                    '    let title = "Payslips" + "/" + "list"\n'
                    '    func getPayslips(url: String) async throws -> PayslipsResult {\n'
                    '        try await api.request(PlainURLRequest<P>(url: url, httpMethod: .GET))\n'
                    '    }\n'
                    '}\n')
        inv = ios.extract(root)
        found = [e for e in inv["endpoints"] if e["path"].endswith("/allpayslips")]
        self.assertEqual(len(found), 1, inv["endpoints"])
        self.assertEqual(found[0]["file"], "Service/PayslipService.swift:3")
        self.assertEqual(found[0]["type"], "PayslipService.payslipUrl")
        self.assertEqual(found[0]["client"], "url-builder")
        self.assertEqual(found[0]["method"], "GET")  # the one method the service sends built URLs with
        self.assertEqual(len(inv["endpoints"]), 1, "a non-URL name is not an endpoint")

    def test_an_event_case_after_blank_lines_has_its_own_line(self):
        # payslips v8: exportAllPayslips was reported at :10 (`public enum Event`), quickSelection and payslipOpen two
        # lines early; `^\s*case` matched from the first blank line above the case
        import os
        root = self.tmp + "/events-app"
        os.makedirs(root + "/Analytics")
        with open(root + "/Analytics/Events.swift", "w") as f:
            f.write("public enum Event: Equatable {\n    case exportAllPayslips\n\n\n    case payslipOpen\n"
                    "    // the start page\n\n    case quickSelection(String)\n}\n")
        lines = {e["name"]: e["file"] for e in ios.extract(root)["events"]}
        self.assertEqual(lines["exportAllPayslips"], "Analytics/Events.swift:2")
        self.assertEqual(lines["payslipOpen"], "Analytics/Events.swift:5")
        self.assertEqual(lines["quickSelection"], "Analytics/Events.swift:8")

    def test_normalize_endpoint_drops_a_note_after_the_path(self):
        from speclib.common import normalize_endpoint
        self.assertEqual(normalize_endpoint("/employee/api/v1/Payslip/Export (single company)"),
                         normalize_endpoint("/employee/api/v1/payslip/export"))
        self.assertEqual(normalize_endpoint("/a/{id}/b (push path only; list passes the loaded item)"), "/a/{}/b")

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
