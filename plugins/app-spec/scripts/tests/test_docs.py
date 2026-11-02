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

    def test_the_skill_says_how_an_agent_answer_reaches_save_json(self):
        # payslips v4: the run searched the subagent transcript folder for a contract batch and was denied
        skill = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("OUT/answers/", skill)
        self.assertIn("Never search session or transcript folders", skill)
        self.assertNotIn("transcript (`.jsonl`)", skill)

    def test_the_skill_says_which_role_writes(self):
        # P9: role prompts say read-only while the path without the Workflow tool needs one agent to save results
        skill = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("**Who writes.**", skill)
        self.assertIn("write nothing while you act in that role", skill)

    def test_agents_name_the_injection_field_the_schemas_have(self):
        # P16: the mapper prompt said "the flags field"; the schema field is injectionSuspects
        for path in sorted((PLUGIN / "agents").glob("*.md")) + sorted((PLUGIN / "workflows").glob("*.js")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("flags field", text, path.name)
            self.assertNotIn("(or flags)", text, path.name)
        mapper = (PLUGIN / "agents" / "use-case-mapper.md").read_text(encoding="utf-8")
        self.assertIn("`injectionSuspects`", mapper)

    def test_structural_appendices_are_never_the_writers(self):
        critic = (PLUGIN / "agents" / "spec-critic.md").read_text(encoding="utf-8")
        self.assertIn("**Appendix A** (fields)", critic)
        self.assertIn("belongs to `analyst`", critic)
        self.assertIn("a missing reason belongs to `person`", critic)
        self.assertIn("writer|person", critic)
        skill = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("A `person` finding (an Appendix F reason, a scope or naming decision) is never sent to an agent", skill)


if __name__ == "__main__":
    unittest.main()
