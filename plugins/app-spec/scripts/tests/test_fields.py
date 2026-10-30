import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import FIX
from speclib import fields

import module

IOS = str(FIX / "ios-app")
ANDROID = str(FIX / "android-app")
RN = str(FIX / "rn-app")
SOURCE_EXTS = (".swift", ".kt", ".tsx", ".ts", ".js", ".jsx")


def core_files(app):
    """Absolute paths of the files of the Payslips module in the iOS fixture."""
    core = module.resolve_by_name(app, "ios-native", ["Payslips"])["core"]
    return [os.path.join(app, f) for f in module.files_under(app, "ios-native", core)]


def all_files(app):
    return [os.path.join(app, rel) for rel, _ in module.walk(app) if rel.endswith(SOURCE_EXTS)]


def screen(result, name):
    return next(x for x in result if x["screen"] == name)


class TestFields(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, rel, text):
        path = Path(self.tmp) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_fields_swiftui_list_screen(self):
        s = next(x for x in fields.extract("ios-native", IOS, core_files(IOS)) if x["screen"] == "PayslipListView")
        kinds = [e["kind"] for e in s["elements"]]
        self.assertEqual(kinds, ["text", "list", "button"])
        self.assertEqual(s["elements"][0]["identifier"], "pay.list.title")
        self.assertEqual(s["elements"][0]["textKey"], "payslip.list.title")

    def test_fields_icon_only_button_has_no_text(self):
        s = next(x for x in fields.extract("ios-native", IOS, core_files(IOS)) if x["screen"] == "PayslipDetailView")
        icon = next(e for e in s["elements"] if e["kind"] == "button" and e["identifier"] is None)
        self.assertIsNone(icon["textKey"])
        self.assertIsNone(icon["text"])

    def test_fields_compose_test_tag_and_string_resource(self):
        s = fields.extract("android-native", ANDROID, all_files(ANDROID))[0]
        self.assertEqual(s["elements"][0]["identifier"], "pay.list.title")
        self.assertEqual(s["elements"][0]["textKey"], "payslip_title")

    def test_fields_rn_test_id(self):
        s = fields.extract("react-native", RN, all_files(RN))[0]
        self.assertEqual(s["elements"][0]["identifier"], "pay.list.title")
        self.assertEqual(s["elements"][0]["textKey"], "payslip.title")

    def test_fields_screen_and_element_positions(self):
        s = screen(fields.extract("ios-native", IOS, core_files(IOS)), "PayslipListView")
        rel, _, line = s["file"].rpartition(":")
        self.assertEqual(rel, "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift")
        self.assertTrue(line.isdigit())
        self.assertEqual(s["elements"][0]["file"], rel)
        self.assertGreater(s["elements"][0]["line"], int(line))

    def test_fields_literal_text_and_null_when_neither_resolves(self):
        s = screen(fields.extract("ios-native", IOS, core_files(IOS)), "PayslipDetailView")
        self.assertEqual([(e["kind"], e["text"], e["textKey"]) for e in s["elements"][:3]],
                         [("text", None, None), ("text", "Net pay", None), ("input", "Search lines", None)])

    def test_fields_identifier_stays_on_its_own_element(self):
        path = self.write("A.swift", 'import SwiftUI\n\nstruct A: View {\n    var body: some View {\n        VStack {\n'
                          '            Text("one")\n            Text("two")\n                .accessibilityIdentifier("two.id")\n'
                          '            Text("three")\n        }\n    }\n}\n')
        s = fields.extract("ios-native", self.tmp, [path])[0]
        self.assertEqual([e["identifier"] for e in s["elements"]], [None, "two.id", None])

    def test_fields_uikit_controller_links_variable_statements(self):
        path = self.write("Pay.swift", 'import UIKit\n\nfinal class PayViewController: UIViewController {\n'
                          '    private let titleLabel = UILabel()\n    private let saveButton = UIButton(type: .system)\n\n'
                          '    override func viewDidLoad() {\n        titleLabel.text = NSLocalizedString("pay.title", comment: "")\n'
                          '        titleLabel.accessibilityIdentifier = "pay.title.label"\n'
                          '        saveButton.setTitle("Save", for: .normal)\n    }\n}\n')
        s = fields.extract("ios-native", self.tmp, [path])[0]
        self.assertEqual(s["screen"], "PayViewController")
        self.assertEqual([(e["kind"], e["textKey"], e["text"], e["identifier"]) for e in s["elements"]],
                         [("text", "pay.title", None, "pay.title.label"), ("button", None, "Save", None)])

    def test_fields_uikit_reused_local_name_keeps_each_element_apart(self):
        path = self.write("Two.swift", 'import UIKit\n\nfinal class TwoViewController: UIViewController {\n'
                          '    lazy var titleLabel: UILabel = {\n        let label = UILabel()\n'
                          '        label.text = NSLocalizedString("pay.title", comment: "")\n'
                          '        label.accessibilityIdentifier = "pay.title.id"\n        return label\n    }()\n\n'
                          '    lazy var subLabel: UILabel = {\n        let label = UILabel()\n'
                          '        label.text = "Sub"\n        return label\n    }()\n}\n')
        s = fields.extract("ios-native", self.tmp, [path])[0]
        self.assertEqual([(e["textKey"], e["text"], e["identifier"]) for e in s["elements"]],
                         [("pay.title", None, "pay.title.id"), (None, "Sub", None)])

    def test_fields_uikit_member_path_does_not_attach_to_a_variable(self):
        path = self.write("Member.swift", 'import UIKit\n\nfinal class MemberViewController: UIViewController {\n'
                          '    private let titleLabel = UILabel()\n\n    override func viewDidLoad() {\n'
                          '        header.titleLabel.text = "x"\n        self.titleLabel.text = "mine"\n    }\n}\n')
        s = fields.extract("ios-native", self.tmp, [path])[0]
        self.assertEqual([e["text"] for e in s["elements"]], ["mine"])

    def test_fields_compose_lambda_content_belongs_to_nested_elements(self):
        path = self.write("S.kt", '@Composable\nfun PayScreen() {\n    Button(onClick = {}, modifier = Modifier.testTag("pay.go")) {\n'
                          '        Text("Go")\n    }\n    LazyColumn {\n    }\n}\n\n@Composable\nfun helper() {\n    Text("x")\n}\n')
        result = fields.extract("android-native", self.tmp, [path])
        self.assertEqual([x["screen"] for x in result], ["PayScreen"])
        self.assertEqual([(e["kind"], e["text"], e["identifier"]) for e in result[0]["elements"]],
                         [("button", None, "pay.go"), ("text", "Go", None), ("list", None, None)])

    def test_fields_rn_default_export_children_and_attributes(self):
        path = self.write("P.tsx", "export default function Pay() {\n  return (\n    <View>\n      <Text>Hello there</Text>\n"
                          "      <TextInput testID={'q'} placeholder=\"Search\" />\n      <Picker.Item label=\"x\" />\n"
                          "      <Pressable testID=\"go\"><Text>{t(\"go.key\")}</Text></Pressable>\n    </View>\n  );\n}\n")
        s = fields.extract("react-native", self.tmp, [path])[0]
        self.assertEqual(s["screen"], "Pay")
        self.assertEqual([(e["kind"], e["text"], e["textKey"], e["identifier"]) for e in s["elements"]],
                         [("text", "Hello there", None, None), ("input", "Search", None, "q"),
                          ("button", None, None, "go"), ("text", None, "go.key", None)])

    def test_fields_unknown_stack_raises(self):
        with self.assertRaises(ValueError):
            fields.extract("cobol", self.tmp, [])


if __name__ == "__main__":
    unittest.main()
