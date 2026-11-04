import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
SOURCE_CHECK = SCRIPTS / "source_check.py"


def run_cli(action, out):
    return subprocess.run(
        [sys.executable, str(SOURCE_CHECK), action, str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def make_git_repo(path):
    path.mkdir(parents=True)
    (path / "tracked.swift").write_text("let value = 1\n", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "app-spec test",
        "GIT_AUTHOR_EMAIL": "app-spec-test@example.invalid",
        "GIT_COMMITTER_NAME": "app-spec test",
        "GIT_COMMITTER_EMAIL": "app-spec-test@example.invalid",
    }
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "add", "tracked.swift"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "fixture"], check=True, env=env)


class TestSourceCheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "out"
        self.out.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, app, contracts=None):
        with (self.out / "app-spec.json").open("w", encoding="utf-8") as destination:
            json.dump({
                "app": {"path": str(app)},
                "contracts": [{"path": str(path)} for path in contracts or []],
            }, destination)

    def save(self):
        result = run_cli("save", self.out)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unchanged_git_folder_verifies(self):
        app = self.root / "app"
        make_git_repo(app)
        self.configure(app)
        self.save()

        result = run_cli("verify", self.out)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Changed folder", result.stdout)

    def test_modified_git_file_is_reported(self):
        app = self.root / "app"
        make_git_repo(app)
        self.configure(app)
        self.save()
        (app / "tracked.swift").write_text("let value = 2\n", encoding="utf-8")

        result = run_cli("verify", self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(app), result.stdout)
        self.assertIn("tracked.swift", result.stdout)

    def test_new_untracked_file_is_reported(self):
        app = self.root / "app"
        make_git_repo(app)
        self.configure(app)
        self.save()
        (app / "new.swift").write_text("let extra = true\n", encoding="utf-8")

        result = run_cli("verify", self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(app), result.stdout)
        self.assertIn("?? new.swift", result.stdout)

    def test_changed_non_git_folder_is_reported(self):
        app = self.root / "app"
        app.mkdir()
        source = app / "tracked.swift"
        source.write_text("let value = 1\n", encoding="utf-8")
        self.configure(app)
        self.save()
        stat = source.stat()
        source.write_text("let value = 2\n", encoding="utf-8")
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

        result = run_cli("verify", self.out)
        self.assertEqual(result.returncode, 1)
        self.assertIn(str(app), result.stdout)

    def test_verify_without_saved_state_exits_two(self):
        result = run_cli("verify", self.out)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no saved source state", result.stderr)


if __name__ == "__main__":
    unittest.main()
