import json
import os
import shutil
import tempfile
import unittest

from helpers import run_cli

import save_json


class TestSaveJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def src(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def save(self, src, *extra):
        dest = os.path.join(self.tmp, "out", "x.json")
        code, stdout, err = run_cli(["save_json.py", src, dest, *extra])
        self.assertEqual(code, 0, err)
        with open(dest, encoding="utf-8") as fh:
            return json.load(fh), stdout

    def test_a_workflow_output_is_unwrapped(self):
        result = {"useCases": [{"name": "View payslips"}], "screens": [], "flows": []}
        src = self.src("task.json", json.dumps({"summary": "3 shards", "result": result}))
        value, stdout = self.save(src, "--key", "useCases")
        self.assertEqual(value, result)
        self.assertIn("object, keys useCases, screens, flows", stdout)
        as_string = self.src("task2.json", json.dumps({"summary": "s", "result": json.dumps(result)}))
        self.assertEqual(self.save(as_string, "--key", "useCases")[0], result)

    def test_the_last_assistant_message_of_a_transcript(self):
        findings = [{"severity": "High", "section": "Screens", "finding": "f", "fix": "x", "owner": "writer"}]
        lines = [
            {"type": "user", "message": {"role": "user", "content": "review it ```json\n[{\"severity\": \"Nit\"}]\n```"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "First draft:\n```json\n[{\"severity\": \"Medium\", \"owner\": \"rules\"}]\n```"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}},
                {"type": "text", "text": "Here are the findings.\n\n```json\n" + json.dumps(findings) + "\n```\nDone."}]}},
        ]
        src = self.src("agent.jsonl", "\n".join(json.dumps(x) for x in lines) + "\n")
        value, _ = self.save(src, "--list")
        self.assertEqual(value, findings)

    def test_an_object_after_a_line_of_prose(self):
        envelope = {"endpoints": [{"id": "EP-001", "label": "INFERRED"}], "disagreements": []}
        src = self.src("reader.txt", "I read every endpoint. The envelope:\n" + json.dumps(envelope) + "\n")
        self.assertEqual(self.save(src, "--key", "endpoints")[0], envelope)

    def test_key_skips_a_later_value_without_it(self):
        text = 'Result: {"endpoints": [{"id": "EP-001"}]}\nAlso see {"note": "x"}'
        self.assertEqual(save_json.pick(text, "endpoints"), {"endpoints": [{"id": "EP-001"}]})
        self.assertEqual(save_json.pick(text), {"note": "x"})

    def test_a_nested_value_is_not_taken_on_its_own(self):
        text = 'Answer: {"rules": [{"name": "a"}], "stats": {"rules": 1}}'
        self.assertEqual(save_json.pick(text, "rules"), {"rules": [{"name": "a"}], "stats": {"rules": 1}})

    def test_no_match_exits_2_and_writes_nothing(self):
        src = self.src("none.txt", "nothing here, not even {broken json")
        dest = os.path.join(self.tmp, "y.json")
        code, _, err = run_cli(["save_json.py", src, dest, "--key", "rules"])
        self.assertEqual(code, 2)
        self.assertIn("with the key rules", err)
        self.assertFalse(os.path.exists(dest))


if __name__ == "__main__":
    unittest.main()
