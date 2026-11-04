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
        skill = " ".join((PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8").split())  # line breaks
        self.assertIn("OUT/answers/", skill)
        self.assertIn("Never search session or transcript folders", skill)
        self.assertNotIn("transcript (`.jsonl`)", skill)
        # payslips v5: a 61.7 KB answer was stored as a file and joined by hand
        self.assertIn("the harness stores it as a file", skill)

    def test_a_rules_finding_corrects_the_named_cards(self):
        # payslips v5: step 7.5 re-ran the extraction on the shard; the new cards were added beside the wrong old ones
        # (87 -> 162 rules) and critic-2 raised the same rule findings again
        skill = " ".join((PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8").split())
        self.assertIn("the rule cards the findings name", skill)
        self.assertIn("keeps each card's name and source file", skill)
        self.assertNotIn("re-run the rules extraction on the shard that holds the cited files (the workflow", skill)

    def test_the_skill_says_which_role_writes(self):
        # P9: role prompts say read-only while the path without the Workflow tool needs one agent to save results
        skill = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("**Who writes.**", skill)
        self.assertIn("write nothing while you act in that role", skill)

    def test_devin_cloud_fallbacks_cover_skill_invocation_tools_and_plugin_folder(self):
        spec = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        review = (PLUGIN / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8")
        status = (PLUGIN / "skills" / "status" / "SKILL.md").read_text(encoding="utf-8")
        readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
        for text in (spec, review, status, readme):
            self.assertIn("Devin cloud runs no plugin hooks", text)
            self.assertIn("module.py`'s first output line", text)
        for text in (review, status, readme):
            self.assertIn("Base directory: <root>/skills/<skill>", text)
            self.assertIn("two levels above", text)
            self.assertIn("sort -V | tail -1", text)
        for text in (spec, readme):
            self.assertIn("content_type", text)
            self.assertIn("user_question", text)
        cloud = " ".join(spec.split())
        self.assertIn("## In Devin cloud", cloud)
        self.assertIn("two levels above the base directory Devin prints", cloud)
        self.assertIn("devin_workflow.mjs", cloud)
        self.assertIn("source_check.py", cloud)
        self.assertIn("devin_session_create", cloud)
        self.assertIn("run app-spec spec on <app> --module X", readme)
        self.assertIn("model-invocable `/app-spec:start`", readme)
        self.assertIn("child Devin sessions with `devin_workflow.mjs`", readme)
        self.assertIn("single-agent", spec)
        self.assertIn("run_subagent` tool or agent profiles", spec)

    def test_cloud_start_skill_and_child_prompt_template_exist(self):
        skill = (PLUGIN / "skills" / "start" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: start", skill)
        self.assertIn("description:", skill)
        self.assertNotIn("disable-model-invocation", skill)
        self.assertIn("app-spec:start", (PLUGIN / "README.md").read_text(encoding="utf-8"))
        self.assertTrue((PLUGIN / "references" / "devin-child.md").is_file())

    def test_single_agent_option_is_documented_and_set_for_cloud_runs(self):
        design = (PLUGIN / "docs" / "DESIGN.md").read_text(encoding="utf-8")
        spec = (PLUGIN / "skills" / "spec" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`options.independence`", design)
        self.assertIn("`separate-agents` (default when absent) or `single-agent`", design)
        self.assertIn('o["independence"]="single-agent"', spec)
        self.assertIn('o.pop("independence",None)', spec)
        self.assertIn("not independent", design)

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
