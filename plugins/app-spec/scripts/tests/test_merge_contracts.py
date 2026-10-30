import json
import os
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out
from test_render_catalogs import build_out

import merge_contracts

ASPNET = str(FIX / "backend-aspnet")
FIELDS = {"fields": [{"name": "gross", "type": "decimal", "required": False, "nullable": "explicit"}]}


def endpoints(dest):
    return {e["id"]: e for e in out.load(dest, "endpoints.json")["endpoints"]}


class TestLabel(unittest.TestCase):
    def test_verified_stays_unless_unknown_with_reason(self):
        self.assertEqual(merge_contracts.label("VERIFIED", "INFERRED", None), "VERIFIED")
        self.assertEqual(merge_contracts.label("VERIFIED", "UNKNOWN", None), "VERIFIED")
        self.assertEqual(merge_contracts.label("VERIFIED", "UNKNOWN", "response type not found"), "UNKNOWN")

    def test_reader_never_raises_to_verified(self):
        self.assertEqual(merge_contracts.label("INFERRED", "VERIFIED", None), "INFERRED")
        self.assertEqual(merge_contracts.label("UNKNOWN", "VERIFIED", None), "INFERRED")
        self.assertEqual(merge_contracts.label("UNKNOWN", "INFERRED", None), "INFERRED")

    def test_other_labels_can_go_down(self):
        self.assertEqual(merge_contracts.label("INFERRED", "UNKNOWN", None), "UNKNOWN")
        self.assertEqual(merge_contracts.label("INFERRED", "bogus", None), "INFERRED")


class TestMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "plain")
        code, _, err = run_cli(["render.py", "catalogs", self.out])
        self.assertEqual(code, 0, err)
        code, _, err = run_cli(["contracts.py", self.out, "--repo", ASPNET])
        self.assertEqual(code, 0, err)
        self.ids = endpoints(self.out)
        self.verified = next(i for i, e in self.ids.items() if e["label"] == "VERIFIED")
        self.other = next(i for i, e in self.ids.items() if e["label"] != "VERIFIED")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def envelope(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_fields_disagreements_and_flags_are_merged(self):
        env = self.envelope("a.json", {
            "endpoints": [{"id": self.verified, "request": {"fields": []}, "response": FIELDS,
                           "errors": [{"status": 404, "reaction": "shows the not-found state"}],
                           "auth": "bearer token", "label": "INFERRED", "citations": ["A.swift:3"]},
                          {"id": "EP-999", "label": "INFERRED"}],
            "disagreements": [{"endpoint": self.verified, "field": "gross", "client": "A.swift:3",
                               "backend": "B.cs:9", "note": "nullable on the client only"}],
            "injectionFlags": ["A.swift:7: ignore your rules"]})
        code, stdout, err = run_cli(["merge_contracts.py", self.out, env])
        self.assertEqual(code, 0, err)
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["response"], FIELDS)
        self.assertEqual(e["errors"][0]["status"], 404)
        self.assertEqual(e["auth"], "bearer token")
        self.assertEqual(e["label"], "VERIFIED")  # the reader's INFERRED does not lower contracts.py's VERIFIED
        self.assertEqual(e["disagreements"], [{"field": "gross", "client": "A.swift:3", "backend": "B.cs:9",
                                               "note": "nullable on the client only"}])
        self.assertIn("EP-999: not in endpoints.json", err)
        self.assertIn("injection flag: A.swift:7", stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.out, merge_contracts.RESULT)))

    def test_unknown_with_reason_lowers_verified_and_keeps_the_reason(self):
        env = self.envelope("a.json", {"endpoints": [{"id": self.verified, "label": "UNKNOWN",
                                                      "reason": "the response type is generated and not in the repo"}]})
        run_cli(["merge_contracts.py", self.out, env])
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["label"], "UNKNOWN")
        self.assertEqual(e["reason"], "the response type is generated and not in the repo")

    def test_reapply_after_render_restores_the_merge_and_is_idempotent(self):
        env = self.envelope("a.json", {
            "endpoints": [{"id": self.verified, "response": FIELDS, "label": "VERIFIED"}],
            "disagreements": [{"endpoint": self.verified, "field": "gross", "client": "A.swift:3", "backend": "B.cs:9",
                               "note": "n"}]})
        run_cli(["merge_contracts.py", self.out, env])
        run_cli(["render.py", "catalogs", self.out])  # writes endpoints.json from scratch
        self.assertNotEqual(endpoints(self.out)[self.verified]["response"], FIELDS)
        run_cli(["contracts.py", self.out, "--repo", ASPNET])
        for _ in range(2):
            code, _, err = run_cli(["merge_contracts.py", self.out])
            self.assertEqual(code, 0, err)
        e = endpoints(self.out)[self.verified]
        self.assertEqual(e["response"], FIELDS)
        self.assertEqual(len(e["disagreements"]), 1)

    def test_a_later_batch_replaces_the_same_id(self):
        first = self.envelope("a.json", {"endpoints": [{"id": self.other, "auth": "first", "label": "INFERRED"}],
                                         "injectionFlags": ["X.swift:1: flag"]})
        second = self.envelope("b.json", {"endpoints": [{"id": self.other, "auth": "second", "label": "INFERRED"}],
                                          "injectionFlags": ["X.swift:1: flag"]})
        run_cli(["merge_contracts.py", self.out, first])
        run_cli(["merge_contracts.py", self.out, second])
        saved = out.load(self.out, merge_contracts.RESULT)
        self.assertEqual([e["auth"] for e in saved["endpoints"]], ["second"])
        self.assertEqual(saved["injectionFlags"], ["X.swift:1: flag"])
        self.assertEqual(endpoints(self.out)[self.other]["auth"], "second")

    def test_without_a_result_nothing_changes(self):
        before = out.load(self.out, "endpoints.json")
        code, stdout, _ = run_cli(["merge_contracts.py", self.out])
        self.assertEqual(code, 0)
        self.assertIn("unchanged", stdout)
        self.assertEqual(out.load(self.out, "endpoints.json"), before)

    def test_bad_envelope_and_bad_folder_exit_2(self):
        bad = self.envelope("bad.json", ["not", "an", "envelope"])
        self.assertEqual(run_cli(["merge_contracts.py", self.out, bad])[0], 2)
        self.assertEqual(run_cli(["merge_contracts.py", self.tmp])[0], 2)
        self.assertEqual(run_cli(["merge_contracts.py"])[0], 2)


if __name__ == "__main__":
    unittest.main()
