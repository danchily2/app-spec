"""The plugin's own words agree with its contract."""

import json
import unittest

from helpers import SCRIPTS

PLUGIN = SCRIPTS.parent


class TestDocs(unittest.TestCase):
    def test_plugin_description_counts_review_rounds_as_the_contract_does(self):
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("two more passes", manifest["description"])
        self.assertIn("up to two review rounds", manifest["description"])

    def test_the_capabilities_file_is_app_fusions_capabilities_json(self):
        for rel in ("skills/spec/SKILL.md", "docs/DESIGN.md"):
            text = (PLUGIN / rel).read_text(encoding="utf-8")
            self.assertNotIn("capability_index.json", text, rel)
            self.assertIn("`capabilities.json`", text, rel)


if __name__ == "__main__":
    unittest.main()
