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
        self.assertEqual(builder.evidence_name("X.MD"), "X.evidence.md")  # the stem keeps its case

    def test_a_dot_before_an_identifier_is_not_glued_to_the_word_before(self):
        text = "Wraps it as .api (`A.swift:3`).\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "Wraps it as .api.\n")

    def test_a_label_left_with_nothing_is_removed(self):
        text = "Rules and endpoints. Sources: `A.swift:3`, `B.swift:4`.\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "Rules and endpoints.\n")
        text = "X (task: `A.swift:3`; quick action keyed by [.payslips]: `B.swift:4`)\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "X\n")

    def test_a_label_with_a_value_and_a_citation_keeps_the_value(self):
        text = "X (task: `A.swift:3`; key [.payslips]: `B.swift:4`; plain: yes)\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "X (plain: yes)\n")

    def test_a_span_keeps_no_trailing_colon_after_its_citation(self):
        text = "Uses `ReportsInterface: Mod/YearEndReports.swift:46` here.\n"
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "Uses `ReportsInterface` here.\n")

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
        self.assertEqual(builder.builder_text(text, "x.evidence.md"),
                         "| CAP | Name | Design |\n|---|---|---|\n| CAP-029 | Browse | carry-as-is |\n")

    def test_dropping_a_middle_column(self):
        text = ("| Name | Source | Type |\n|---|---|---|\n| id | `A.swift:3` | String |\n")
        self.assertEqual(builder.builder_text(text, "x.evidence.md"), "| Name | Type |\n|---|---|\n| id | String |\n")

    def test_label_followed_by_real_text_is_kept(self):
        self.assertEqual(builder.builder_text("Source: real text `A.swift:3`\n", "x.evidence.md"),
                         "Source: real text\n")
        self.assertEqual(builder.builder_text("Note Searched: Reports/ x `A.swift:3`.\n", "x.evidence.md"),
                         "Note Searched: Reports/ x.\n")

    def test_citation_at_the_end_of_a_list_leaves_no_connector(self):
        self.assertEqual(builder.builder_text("Shown (used by X, `A.swift:3`).\n", "x.evidence.md"),
                         "Shown (used by X).\n")
        self.assertEqual(builder.builder_text("Used by X, see `A.swift:3`.\n", "x.evidence.md"), "Used by X.\n")

    def test_citation_inside_a_longer_code_span_leaves_no_empty_span(self):
        self.assertEqual(builder.builder_text("It is carry-as-is (`me-ios Mod/A.swift:3`) here.\n", "x.evidence.md"),
                         "It is carry-as-is here.\n")
        self.assertEqual(builder.builder_text("See `Foo A.swift:3` now.\n", "x.evidence.md"), "See now.\n")
        self.assertEqual(builder.builder_text("Run `make A.swift:3 all` now.\n", "x.evidence.md"),
                         "Run `make all` now.\n")

    def test_sentence_made_of_citations_has_no_doubled_spaces(self):
        self.assertEqual(builder.builder_text("It is defined in `A.swift:3` and `B.swift:4`.\n", "x.evidence.md"),
                         "It is defined in and.\n")

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
