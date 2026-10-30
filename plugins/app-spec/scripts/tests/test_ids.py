import json
import os
import shutil
import tempfile
import unittest

import helpers  # noqa: F401  (puts the scripts folder on sys.path)
from speclib import ids


class TestNorm(unittest.TestCase):
    def test_norm_lowercases_collapses_and_drops_articles(self):
        self.assertEqual(ids.norm("View a Payslip's Details"), "view payslip s details")
        self.assertEqual(ids.norm("  The   Payslip-list! "), "payslip list")
        self.assertEqual(ids.norm("An"), "")
        self.assertEqual(ids.norm("Anything about Theme"), "anything about theme")  # whole words only

    def test_norm_keeps_unicode_letters(self):
        self.assertEqual(ids.norm("Visa lönespecifikation"), "visa lönespecifikation")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "ids.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_ids_are_stable_and_never_reused(self):
        r = ids.Registry(self.path)
        a = r.assign("UC", "view payslip")
        b = r.assign("UC", "download pdf")
        r.save()
        r2 = ids.Registry(self.path)
        self.assertEqual(r2.assign("UC", "view payslip"), a)
        self.assertEqual(r2.assign("UC", "new thing"), "UC-003")
        self.assertNotEqual(r2.assign("UC", "new thing"), b)

    def test_a_retired_key_stays_and_its_number_is_not_reissued(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"UC": {"old": "UC-005"}, "max": {"UC": 7}}, fh)
        r = ids.Registry(self.path)
        self.assertEqual(r.assign("UC", "fresh"), "UC-008")  # max wins over the highest id in the map
        r.save()
        saved = self.read()
        self.assertEqual(saved["UC"]["old"], "UC-005")
        self.assertEqual(saved["max"]["UC"], 8)

    def test_prefixes_count_apart_and_have_three_digits(self):
        r = ids.Registry(self.path)
        self.assertEqual(r.assign("SCR", "a|x"), "SCR-001")
        self.assertEqual(r.assign("EP", "GET /a"), "EP-001")
        self.assertEqual(r.assign("UC", "b"), "UC-001")

    def test_save_writes_every_class_map_and_max(self):
        r = ids.Registry(self.path)
        r.assign("UC", "a")
        r.save()
        saved = self.read()
        for prefix in ("UC", "SCR", "FLOW", "RULE", "EP"):
            self.assertIn(prefix, saved)
        self.assertEqual(saved["max"]["UC"], 1)


if __name__ == "__main__":
    unittest.main()
