"""The builder spec is the evidence spec with every citation taken out and nothing else changed."""

import unittest

from helpers import SCRIPTS  # noqa: F401  (puts the scripts folder on sys.path)
from speclib import builder, template


class TestBuilder(unittest.TestCase):
    def test_evidence_name(self):
        self.assertEqual(builder.evidence_name("payslips.md"), "payslips.evidence.md")
        self.assertEqual(builder.evidence_name("SPEC.md"), "SPEC.evidence.md")
        self.assertEqual(builder.evidence_name("docs/a.md"), "docs/a.evidence.md")
        self.assertEqual(builder.evidence_name("notes"), "notes.evidence.md")

    def test_citation_lists_in_parentheses_leave_no_debris(self):
        line = ("The list pages back only (`A/B.swift:3`, `C/D.swift:9-12`). "
                "It stops at the end (cites `E.swift:4` and `F.kt:7`).")
        self.assertEqual(builder.builder_text(line + "\n", "x.evidence.md"),
                         "The list pages back only. It stops at the end.\n")

    def test_source_label_with_only_a_citation_is_removed(self):
        text = "An employee reads their payslips. Source: `Mod/List.swift:8`\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "An employee reads their payslips.\n")

    def test_source_bullet_is_dropped(self):
        text = ("- **Rule:** Shows the card.\n"
                "- **Source:** `Employee/StartPage/StartPageViewModel.swift:211-219`\n")
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "- **Rule:** Shows the card.\n")

    def test_dropping_a_column_keeps_rows_aligned(self):
        text = ("| Name | Type | Source |\n|---|---|---|\n"
                "| id | String | `A.swift:3` |\n| note | String a \\| b | `B.swift:4` |\n")
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "| Name | Type |\n|---|---|\n| id | String |\n| note | String a \\| b |\n")

    def test_design_column_loses_its_citation(self):
        text = ("| CAP | Name | Design |\n|---|---|---|\n"
                "| CAP-029 | Browse | carry-as-is (me-ios Mod/Paging.swift:59-124) |\n")
        self.assertIn("| CAP-029 | Browse | carry-as-is |", builder.builder_text(text, "x.evidence.md"))

    def test_unknown_keeps_owner_drops_search_note(self):
        text = "- **Client:** UNKNOWN; searched: Reports/, grep exportYearEnd; owner: backend team\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "- **Client:** UNKNOWN; owner: backend team\n")

    def test_citation_with_a_comma_list_of_lines_is_removed_whole(self):
        text = "Disagreement: client `A/B.swift:20,40`, backend `C.cs:6`. Types differ.\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "Disagreement: client, backend. Types differ.\n")

    def test_bare_citation_lists_and_a_leading_citation_in_parentheses(self):
        text = ("Kept as pending (A/B.swift:187,191-194,381). "
                "The shape matches the old one (C/D.cs:35-139, used by the obsolete route).\n")
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "Kept as pending. The shape matches the old one (used by the obsolete route).\n")

    def test_searched_label_with_only_a_citation_is_removed(self):
        text = "- **OQ-014:** Must it stay? (RULE-100) Searched: `A/B.swift:3`. Owner: owner of me-ios.\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "- **OQ-014:** Must it stay? (RULE-100) Owner: owner of me-ios.\n")

    def test_endpoint_paths_are_not_citations(self):
        text = "Calls `GET /v1/payslips/{id}` and `GET /v1/reports`.\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), text)

    def test_fenced_code_is_unchanged(self):
        text = "```\nsee `A.swift:3`\n```\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), text)

    def test_header_drops_module_scope(self):
        text = ("# M spec\n\nSource: module M of me-ios\nReference HEADs: me-ios `abc`\n\n"
                "Module scope:\n- Core: 2 files in `Employee/X`\n- Touch point: `Employee/Y.swift` (uses type Z).\n\n"
                "## Summary\n")
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "# M spec\n\nSource: module M of me-ios\nReference HEADs: me-ios `abc`\n\n## Summary\n")

    def test_appendix_f_points_to_the_evidence_file(self):
        text = f"{template.APPENDICES[5]}\n\n| Class | Covered |\n|---|---|\n| screens | 25 |\n"
        self.assertEqual(builder.builder_text(text, "payslips.evidence.md"),
                         f"{template.APPENDICES[5]}\n\nCoverage evidence and every citation: `payslips.evidence.md`.\n")


if __name__ == "__main__":
    unittest.main()
