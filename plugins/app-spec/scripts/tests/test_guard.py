"""The source write guard: file tools are denied under the analysed app and contract repositories, shell writes there
are sent to the person, everything else passes."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import helpers  # noqa: F401  (puts the scripts folder on sys.path)

SCRIPTS = str(helpers.SCRIPTS)
PLUGIN = os.path.dirname(SCRIPTS)
GUARD = os.path.join(SCRIPTS, "guard.py")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "DEVIN_", "APP_SPEC_"))}
    env.update(extra)
    return env


class GuardBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = os.path.realpath(self.tmp.name)
        self.OUT = os.path.join(base, "out")
        self.APP = os.path.join(base, "me-ios")
        self.BACKEND = os.path.join(base, "me-api")
        self.OTHER = os.path.join(base, "elsewhere")
        for d in (self.OUT, self.APP, self.BACKEND, self.OTHER):
            os.makedirs(d)
        with open(os.path.join(self.APP, "Main.swift"), "w") as fh:
            fh.write("// app\n")
        cfg = {"version": 1, "app": {"path": self.APP, "name": "me-ios"}, "contracts": [{"path": self.BACKEND, "name": "me-api"}]}
        with open(os.path.join(self.OUT, "app-spec.json"), "w") as fh:
            json.dump(cfg, fh)

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, payload, cwd=None, project=None, script=GUARD, **env):
        full = {"cwd": cwd or self.OUT, **payload}
        extra = dict(env)
        if project:
            extra["CLAUDE_PROJECT_DIR"] = project
        out = subprocess.run([sys.executable, script] if script.endswith(".py") else ["sh", script], input=json.dumps(full),
                             capture_output=True, text=True, env=clean_env(**extra), cwd=self.OTHER)
        self.assertEqual(out.returncode, 0, out.stderr)
        if not out.stdout.strip():
            return None
        hook = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "PreToolUse")
        return {"decision": hook["permissionDecision"], "reason": hook["permissionDecisionReason"]}

    def bash(self, command, **kw):
        return self.run_guard({"tool_name": "Bash", "tool_input": {"command": command}}, **kw)


class FileTools(GuardBase):
    def test_write_under_app_is_denied(self):
        got = self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}, cwd=self.OUT)
        self.assertEqual(got["decision"], "deny")
        self.assertIn(self.APP, got["reason"])
        self.assertIn("app-spec never edits the source app", got["reason"])

    def test_write_under_out_is_allowed(self):
        self.assertIsNone(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.OUT + "/SPEC.md"}}, cwd=self.OUT))
        self.assertIsNone(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.OUT + "/overrides.json"}}, cwd=self.OUT))

    def test_contract_repo_is_protected(self):
        self.assertEqual(self.run_guard({"tool_name": "Edit", "tool_input": {"file_path": self.BACKEND + "/c.cs"}}, cwd=self.OUT)["decision"], "deny")

    def test_other_file_tools_and_devin_names(self):
        for tool, key in (("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path"), ("edit", "file_path"), ("write", "path"),
                          ("notebook_edit", "notebook_path")):
            got = self.run_guard({"tool_name": tool, "tool_input": {key: self.APP + "/n"}})
            self.assertEqual(got["decision"], "deny", tool)

    def test_apply_patch_names_every_file(self):
        patch = f"*** Begin Patch\n*** Add File: {self.OUT}/a.md\n+x\n*** Update File: {self.APP}/Main.swift\n@@\n-a\n+b\n*** End Patch\n"
        self.assertEqual(self.run_guard({"tool_name": "apply_patch", "tool_input": {"input": patch}})["decision"], "deny")
        ok = f"*** Begin Patch\n*** Add File: {self.OUT}/a.md\n+x\n*** End Patch\n"
        self.assertIsNone(self.run_guard({"tool_name": "apply_patch", "tool_input": {"input": ok}}))

    def test_a_link_into_the_app_is_followed(self):
        link = os.path.join(self.OUT, "app-link")
        os.symlink(self.APP, link)
        self.assertEqual(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": link + "/y.swift"}})["decision"], "deny")

    def test_paths_are_compared_without_regard_to_case_on_macos(self):
        if sys.platform != "darwin":
            self.skipTest("case folding is macOS and Windows only")
        got = self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP.upper() + "/x.swift"}})
        self.assertEqual(got["decision"], "deny")

    def test_a_tool_that_is_not_a_writer_passes(self):
        self.assertIsNone(self.run_guard({"tool_name": "Read", "tool_input": {"file_path": self.APP + "/Main.swift"}}))
        self.assertIsNone(self.run_guard({"tool_name": "read", "tool_input": {"file_path": self.APP + "/Main.swift"}}))


class Shell(GuardBase):
    def test_shell_copy_into_app_asks(self):
        self.assertEqual(self.bash(f"cp a {self.APP}/b", cwd=self.OUT)["decision"], "ask")

    def test_redirect_into_app_asks(self):
        self.assertEqual(self.bash(f"echo x > {self.APP}/y")["decision"], "ask")
        self.assertEqual(self.bash(f"echo x >> {self.BACKEND}/y")["decision"], "ask")

    def test_cd_into_app_then_redirect_asks(self):
        self.assertEqual(self.bash(f"cd {self.APP} && echo x > y")["decision"], "ask")
        self.assertEqual(self.bash(f"cd {self.APP}; touch y")["decision"], "ask")

    def test_heredoc_into_app_asks(self):
        self.assertEqual(self.bash(f"cat > {self.APP}/n.swift <<'EOF'\nlet a = 1\nEOF")["decision"], "ask")
        self.assertEqual(self.bash(f"python3 - <<'EOF'\nopen('{self.APP}/z.txt', 'w').write('x')\nEOF")["decision"], "ask")

    def test_wrappers_and_nested_shells_are_read(self):
        self.assertEqual(self.bash(f"sudo rm -rf {self.APP}/build")["decision"], "ask")
        self.assertEqual(self.bash(f"bash -c 'mv a {self.APP}/b'")["decision"], "ask")
        self.assertEqual(self.bash(f"env FOO=1 tee {self.APP}/log < /dev/null")["decision"], "ask")

    def test_a_build_tool_in_the_app_asks_and_git_write_in_it_asks(self):
        self.assertEqual(self.bash("yarn install", cwd=self.APP, project=self.OUT)["decision"], "ask")
        self.assertEqual(self.bash(f"git -C {self.APP} commit -m x")["decision"], "ask")
        self.assertEqual(self.bash(f"sed -i s/a/b/ {self.APP}/Main.swift")["decision"], "ask")

    def test_removing_a_folder_above_the_app_asks(self):
        self.assertEqual(self.bash(f"rm -rf {os.path.dirname(self.APP)}/me-ios")["decision"], "ask")
        self.assertEqual(self.bash(f"rm -rf {os.path.dirname(self.APP)}")["decision"], "ask")

    def test_reads_and_output_folder_writes_pass(self):
        self.assertIsNone(self.bash(f"grep -rn Foo {self.APP}/Main.swift"))
        self.assertIsNone(self.bash(f"cat {self.APP}/Main.swift > {self.OUT}/copy.txt"))
        self.assertIsNone(self.bash(f"cp {self.APP}/Main.swift {self.OUT}/copy.txt"))
        self.assertIsNone(self.bash(f"git -C {self.APP} log --oneline"))
        self.assertIsNone(self.bash(f"cd {self.APP} && git status"))
        self.assertIsNone(self.bash(f"echo x > {self.OUT}/notes.md"))
        self.assertIsNone(self.bash("python3 scripts/render.py --out .", cwd=self.OUT))

    def test_devin_shell_tools(self):
        self.assertEqual(self.run_guard({"tool_name": "exec", "tool_input": {"command": f"echo x > {self.APP}/y"}})["decision"], "ask")
        self.assertEqual(self.run_guard({"tool_name": "exec", "tool_input": {"command": "touch y", "workdir": self.APP}}, project=self.OUT)["decision"], "ask")
        self.assertEqual(self.run_guard({"tool_name": "write_to_process", "tool_input": {"shell_id": "s", "text_input": f"rm -rf {self.APP}/x\n"}})["decision"], "ask")
        self.assertIsNone(self.run_guard({"tool_name": "exec", "tool_input": {"command": "ls", "workdir": self.OUT}}))

    def test_an_unresolvable_write_that_names_the_app_asks(self):
        self.assertEqual(self.bash(f"cp a $DEST && ls {self.APP}")["decision"], "ask")
        self.assertIsNone(self.bash("cp a $DEST"))


class GitFromTheOutputFolder(GuardBase):
    """The output folder may lie inside the app's repository: a git write there still rewrites the app."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.APP, ".git"))
        self.INNER = os.path.join(self.APP, "spec-out")
        os.makedirs(self.INNER)
        with open(os.path.join(self.INNER, "app-spec.json"), "w") as fh:
            json.dump({"version": 1, "app": {"path": self.APP}, "contracts": []}, fh)
        self.UNRELATED = os.path.join(os.path.dirname(self.APP), "other-repo")
        os.makedirs(os.path.join(self.UNRELATED, ".git"))

    def test_whole_tree_git_writes_from_the_output_folder_ask(self):
        for cmd in ("git reset --hard HEAD~1", "git checkout main", "git stash", "git clean -fdx", "git switch main",
                    "git restore .", "git apply x.patch", "git am x.mbox", "git merge main", "git rebase main", "git pull",
                    "git cherry-pick abc", "git revert abc", "git rm -r .", "git mv a b", "git commit -a -m x"):
            got = self.bash(cmd, cwd=self.INNER, project=self.INNER)
            self.assertIsNotNone(got, cmd)
            self.assertEqual(got["decision"], "ask", cmd)

    def test_git_dash_c_from_outside_asks(self):
        self.assertEqual(self.bash(f"git -C {self.INNER} reset --hard", cwd=self.OTHER, project=self.INNER)["decision"], "ask")
        self.assertEqual(self.bash(f"cd {self.INNER} && git clean -fdx", cwd=self.OTHER, project=self.INNER)["decision"], "ask")
        self.assertEqual(self.bash(f"git --work-tree={self.INNER} checkout .", cwd=self.OTHER, project=self.INNER)["decision"], "ask")

    def test_a_repository_above_a_protected_root_asks(self):
        monorepo = os.path.dirname(self.APP)
        os.makedirs(os.path.join(monorepo, ".git"))
        self.assertEqual(self.bash("git reset --hard", cwd=self.OUT)["decision"], "ask")

    def test_git_in_an_unrelated_repository_and_reads_pass(self):
        self.assertIsNone(self.bash("git reset --hard", cwd=self.UNRELATED, project=self.INNER))
        self.assertIsNone(self.bash(f"git -C {self.UNRELATED} checkout main", cwd=self.INNER, project=self.INNER))
        self.assertIsNone(self.bash("git status", cwd=self.APP, project=self.INNER))
        self.assertIsNone(self.bash("git status", cwd=self.INNER, project=self.INNER))
        self.assertIsNone(self.bash("git log --oneline", cwd=self.INNER, project=self.INNER))
        self.assertIsNone(self.bash("git diff", cwd=self.INNER, project=self.INNER))


class Discovery(GuardBase):
    def test_no_config_means_no_decision(self):
        os.remove(os.path.join(self.OUT, "app-spec.json"))
        self.assertIsNone(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}))
        self.assertIsNone(self.bash(f"rm -rf {self.APP}"))

    def test_the_guard_is_disabled_by_env(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}
        self.assertIsNone(self.run_guard(payload, APP_SPEC_GUARD="false"))
        self.assertIsNone(self.run_guard(payload, CLAUDE_PLUGIN_OPTION_GUARD="false"))
        self.assertEqual(self.run_guard(payload, APP_SPEC_GUARD="true")["decision"], "deny")

    def test_config_found_from_the_project_folder_when_cwd_is_elsewhere(self):
        payload = {"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}
        self.assertEqual(self.run_guard(payload, cwd=self.OTHER, project=self.OUT)["decision"], "deny")

    def test_config_found_one_level_below_the_project_folder(self):
        base = os.path.dirname(self.OUT)
        payload = {"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}
        self.assertEqual(self.run_guard(payload, cwd=self.OTHER, project=base)["decision"], "deny")

    def test_config_found_from_a_subfolder_of_the_output_folder(self):
        sub = os.path.join(self.OUT, "shards")
        os.makedirs(sub)
        self.assertEqual(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x"}}, cwd=sub)["decision"], "deny")

    def test_config_found_from_a_path_the_call_names(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": f"cp a {self.APP}/b; ls {self.OUT}/SPEC.md"}}
        self.assertEqual(self.run_guard(payload, cwd=self.OTHER)["decision"], "ask")
        # a file tool's path is the only mention: the folder of a path the call names is searched up to the root
        inside = os.path.join(self.OUT, "notes")
        os.makedirs(inside)
        self.assertEqual(self.run_guard({"tool_name": "Bash", "tool_input": {"command": f"cp {inside}/a {self.APP}/b"}}, cwd=self.OTHER)["decision"], "ask")

    def test_a_broken_config_or_bad_input_never_blocks(self):
        with open(os.path.join(self.OUT, "app-spec.json"), "w") as fh:
            fh.write("{not json")
        self.assertIsNone(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x"}}))
        out = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True, text=True, env=clean_env())
        self.assertEqual((out.returncode, out.stdout), (0, ""))

    def test_relative_roots_in_the_config_resolve_against_the_output_folder(self):
        with open(os.path.join(self.OUT, "app-spec.json"), "w") as fh:
            json.dump({"version": 1, "app": {"path": "../me-ios"}, "contracts": [{"path": "../me-api"}, {"name": "no-path"}, "junk"]}, fh)
        self.assertEqual(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x"}})["decision"], "deny")
        self.assertEqual(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.BACKEND + "/x"}})["decision"], "deny")

    def test_an_output_folder_inside_the_app_stays_writable(self):
        inner = os.path.join(self.APP, "spec-out")
        os.makedirs(inner)
        with open(os.path.join(inner, "app-spec.json"), "w") as fh:
            json.dump({"version": 1, "app": {"path": self.APP}, "contracts": []}, fh)
        self.assertIsNone(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": inner + "/SPEC.md"}}, cwd=inner))
        self.assertEqual(self.run_guard({"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}, cwd=inner)["decision"], "deny")

    def test_protected_roots(self):
        import guard
        roots = guard.protected_roots({"app": {"path": self.APP}, "contracts": [{"path": self.BACKEND}, {"name": "x"}]})
        self.assertEqual(roots, [self.APP, self.BACKEND])
        self.assertEqual(guard.protected_roots({}), [])
        self.assertEqual(guard.protected_roots({"app": "x", "contracts": "y"}), [])


class Hooks(GuardBase):
    def test_guard_sh_under_claude_code_and_devin(self):
        sh = os.path.join(PLUGIN, "hooks", "guard.sh")
        payload = {"tool_name": "Write", "tool_input": {"file_path": self.APP + "/x.swift"}}
        self.assertEqual(self.run_guard(payload, script=sh, CLAUDE_PLUGIN_ROOT=PLUGIN)["decision"], "deny")
        devin = {"tool_name": "write", "tool_input": {"file_path": self.APP + "/x.swift"}}
        self.assertEqual(self.run_guard(devin, script=sh, DEVIN_PLUGIN_ROOT=PLUGIN, DEVIN_PROJECT_DIR=self.OUT)["decision"], "deny")
        self.assertIsNone(self.run_guard(devin, script=sh, DEVIN_PLUGIN_ROOT=PLUGIN, APP_SPEC_GUARD="false"))

    def test_hooks_json_registers_the_guard_and_the_session_note(self):
        with open(os.path.join(PLUGIN, "hooks", "hooks.json")) as fh:
            cfg = json.load(fh)["hooks"]
        pre = cfg["PreToolUse"][0]
        self.assertEqual(pre["matcher"], "Edit|Write|MultiEdit|NotebookEdit|Bash|^(edit|write|notebook_edit|apply_patch|exec|write_to_process)$")
        self.assertEqual(pre["hooks"][0]["command"], 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh"')
        self.assertEqual(pre["hooks"][0]["timeout"], 10)
        start = cfg["SessionStart"][0]["hooks"][0]
        self.assertEqual(start["command"], 'sh "${CLAUDE_PLUGIN_ROOT}/hooks/devin-context.sh"')
        self.assertEqual(start["timeout"], 10)


if __name__ == "__main__":
    unittest.main()
