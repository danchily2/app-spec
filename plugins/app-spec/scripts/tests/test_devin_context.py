"""The Devin session note: printed only under Devin, names the plugin folder and cloud adaptations."""

import json
import os
import subprocess
import sys
import unittest

import helpers  # noqa: F401

SCRIPTS = str(helpers.SCRIPTS)
PLUGIN = os.path.dirname(SCRIPTS)


def run_devin_context(env, via_sh=False):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "DEVIN_", "APP_SPEC_"))}
    base.update(env)
    cmd = ["sh", os.path.join(PLUGIN, "hooks", "devin-context.sh")] if via_sh else [sys.executable, os.path.join(SCRIPTS, "devin_context.py")]
    out = subprocess.run(cmd, input="{}", capture_output=True, text=True, env=base)
    assert out.returncode == 0, out.stderr
    return out.stdout


class DevinContext(unittest.TestCase):
    def test_devin_context_silent_outside_devin(self):
        self.assertEqual(run_devin_context(env={}), "")
        self.assertEqual(run_devin_context(env={"CLAUDE_PLUGIN_ROOT": PLUGIN}, via_sh=True), "")

    def test_devin_context_names_plugin_root(self):
        self.assertIn("app-spec", run_devin_context(env={"DEVIN_PLUGIN_ROOT": "/p"}))

    def test_the_note_maps_the_tools(self):
        hook = json.loads(run_devin_context(env={"DEVIN_PLUGIN_ROOT": PLUGIN, "DEVIN_PROJECT_DIR": "/x"}, via_sh=True))["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "SessionStart")
        text = hook["additionalContext"]
        for word in (os.path.realpath(PLUGIN), f"Base directory: {os.path.realpath(PLUGIN)}/skills/<skill>",
                     "ask_user_question", "run_subagent", "app-spec:", "Without the Workflow tool", "exec",
                     "read", "write", "edit", "grep", "glob", "APP_SPEC_GUARD=false", ".devin/config.json",
                     "Devin cloud runs no plugin hooks", "content_type` is `user_question", "single-agent",
                     "skills/start/SKILL.md", "devin_workflow.mjs", "devin_session_create", "source_check.py",
                     "sort -V | tail -1"):
            self.assertIn(word, text)
        self.assertNotIn("app-fusion", text.lower())
        self.assertNotIn("<root>", text)

    def test_either_variable_alone_is_enough(self):
        self.assertIn("app-spec", run_devin_context(env={"DEVIN_PROJECT_DIR": "/x"}))


if __name__ == "__main__":
    unittest.main()
