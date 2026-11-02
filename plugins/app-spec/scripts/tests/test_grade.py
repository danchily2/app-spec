import os
import shutil
import tempfile
import unittest

from helpers import run_cli
from speclib import out
from test_render_catalogs import build_out, read_text, write_overrides

import grade
import render

LIST = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipListView.swift"
DETAIL = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipDetailView.swift"
ITEM = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift"
GETTER = "EmployeeServices/Payslips/Sources/Payslips/GetPayslips.swift"


def edit(dest, name, change):
    data = out.load(dest, name)
    change(data)
    out.save(dest, name, data)


def full_prose():
    """Every slot filled, a criterion per use case, every cited line inside a fixture file."""
    return {
        "summary": f"An employee reads their payslips. Source: `{LIST}:8`",
        "screens": {
            "SCR-001": {"purpose": "List the payslips of the year.",
                        "states": [{"name": "empty", "shows": "No payslips yet", "evidence": f"`{LIST}:12`"}]},
            "SCR-002": {"purpose": "Show one payslip line by line.",
                        "states": [{"name": "loaded", "shows": "The lines", "evidence": f"`{DETAIL}:9`"}]},
        },
        "keepDrop": {uc: {"keep": ["newest first"], "drop": [{"what": "the list holder", "file": f"{LIST}:3"}]}
                     for uc in ("UC-001", "UC-002", "UC-003")},
        "data": [{"entity": "Payslip", "fields": "id, date", "storage": "none", "lifetime": "session",
                  "evidence": f"`{ITEM}:3`"}],
        "dependencies": [f"The Employee API stays as it is. Source: `{GETTER}:6`"],
        "openQuestions": [{"id": "Q-1", "question": "Is gross shown to part-timers?", "searched": ITEM,
                           "owner": "payroll"}],
        "criteria": [
            {"ids": ["UC-001"], "text": "The newest payslip is on top.", "evidence": f"`{ITEM}:10-14`"},
            {"ids": ["UC-002"], "text": "Tapping a row opens its details.", "evidence": f"`{LIST}:14`"},
            {"ids": ["UC-003"], "text": f"{grade.NO_RULE} Pulling down reloads the list.", "evidence": f"`{LIST}:12`"},
        ],
    }


def make_good(tmp, name="good"):
    """The ios fixture rendered with a complete prose.json and complete catalogs: nothing is left to the writer."""
    dest = build_out(tmp, name)
    render.catalogs(dest)

    def rules(data):
        for r in data["rules"]:
            r["source"] = f"{ITEM}:10-14" if r["id"] == "RULE-001" else f"{DETAIL}:9"
        data["rules"][1].update(useCase="UC-002", confidence="High", question=None)

    def endpoints(data):
        for e in data["endpoints"]:
            e.update(label="INFERRED", auth="bearer", response={"fields": [{"name": "id", "type": "string",
                                                                           "required": True, "nullable": "no"}]},
                     errors=[{"status": 401, "reaction": "sign out"}],
                     backend={"repo": "me-api", "file": GETTER, "line": 6, "auth": "bearer"})

    edit(dest, "rules.json", rules)
    edit(dest, "endpoints.json", endpoints)
    out.save(dest, "prose.json", full_prose())
    render.spec(dest)
    return dest


def check(result, name):
    return next(c for c in result["checks"] if c["name"] == name)


class GradeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.good = make_good(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def copy(self, name):
        dest = os.path.join(self.tmp, name)
        shutil.rmtree(dest, True)
        shutil.copytree(self.good, dest)
        self.addCleanup(shutil.rmtree, dest, True)
        return dest

    def mutated(self, name, change):
        """A copy of the good folder whose SPEC.md went through `change(text)`."""
        dest = self.copy(name)
        out.save_text(dest, "SPEC.md", change(read_text(dest, "SPEC.md")))
        return dest

    def failing(self, dest):
        return [c["name"] for c in grade.run(dest)["checks"] if not c["pass"]]


class TestBrief(GradeCase):
    def test_good_spec_passes_all(self):
        result = grade.run(self.good)
        self.assertEqual([c for c in result["checks"] if not c["pass"]], [])
        self.assertTrue(result["pass"])
        self.assertEqual([c["name"] for c in result["checks"]], list(grade.CHECKS))
        self.assertEqual(out.load(self.good, "grade.json"), result)
        self.assertEqual(result["version"], 1)

    def test_citation_beyond_file_length_fails(self):
        dest = self.mutated("cite9999", lambda t: t.replace(f"`{LIST}:12`", f"`{LIST}:9999`", 1))
        c = check(grade.run(dest), "citations-resolve")
        self.assertFalse(c["pass"])
        self.assertIn(":9999", c["detail"])

    def test_override_unknown_id_is_drift_not_silence(self):
        dest = self.copy("ghost")
        write_overrides(dest, {"drop": [{"kind": "field", "id": "SCR-099.ghost", "reason": "x"}]})
        c = check(grade.run(dest), "overrides-reflected")
        self.assertFalse(c["pass"])
        self.assertIn("SCR-099.ghost", c["detail"])

    def test_banned_noun_in_requirements_fails_but_appendix_c_is_allowed(self):
        screens = self.mutated("realm_screens", lambda t: t.replace("List the payslips of the year.",
                                                                    "List the payslips from the Realm store."))
        self.assertFalse(check(grade.run(screens), "banned-nouns")["pass"])
        appendix_c = self.mutated("realm_c", lambda t: t.replace("the list holder", "the Realm list holder"))
        self.assertIn("Realm list holder", read_text(appendix_c, "SPEC.md"))
        self.assertTrue(check(grade.run(appendix_c), "banned-nouns")["pass"])

    def test_criteria_gap_fails(self):
        def gap(text):
            return text.replace("**AC2 (", "**AC3 (", 1).replace("**AC3 (UC-003)", "**AC4 (UC-003)", 1)
        c = check(grade.run(self.mutated("gap", gap)), "criteria-numbering")
        self.assertFalse(c["pass"])
        self.assertIn("AC3", c["detail"])


class TestOtherChecks(GradeCase):
    def test_sections_missing_swapped_and_extra(self):
        missing = self.mutated("s_missing", lambda t: t.replace("## Dependencies and decisions\n", "## Dependencies\n"))
        c = check(grade.run(missing), "sections")
        self.assertFalse(c["pass"])
        self.assertIn("missing ## Dependencies and decisions", c["detail"])
        self.assertIn("unexpected ## Dependencies", c["detail"])

        def swap(text):
            return text.replace("## Endpoints", "## @@").replace("## Screens", "## Endpoints").replace("## @@", "## Screens")
        c = check(grade.run(self.mutated("s_swap", swap)), "sections")
        self.assertIn("out of order", c["detail"])

    def test_heading_in_a_code_block_is_not_a_heading(self):
        dest = self.mutated("s_code", lambda t: t.replace("## Appendix F. Coverage", "```\n## Not a heading\n```\n\n## Appendix F. Coverage"))
        self.assertTrue(check(grade.run(dest), "sections")["pass"])

    def test_rules_per_use_case(self):
        dest = self.mutated("r_none", lambda t: t.replace(grade.NO_RULE, "Nothing to add."))
        c = check(grade.run(dest), "rules-per-use-case")
        self.assertFalse(c["pass"])
        self.assertIn("UC-003", c["detail"])
        self.assertNotIn("UC-001", c["detail"])
        self.assertNotIn("UC-002", c["detail"])

    def test_the_sentence_needs_a_citation_on_its_line(self):
        dest = self.copy("r_nocite")
        prose = out.load(dest, "prose.json")
        prose["criteria"][2]["evidence"] = "none"
        out.save(dest, "prose.json", prose)
        render.spec(dest)
        c = check(grade.run(dest), "rules-per-use-case")
        self.assertFalse(c["pass"])
        self.assertIn("UC-003", c["detail"])

    def test_the_sentence_in_a_screen_section_counts(self):
        dest = self.copy("r_screen")
        prose = out.load(dest, "prose.json")
        prose["criteria"][2]["text"] = "Pulling down reloads the list."
        prose["screens"]["SCR-001"]["purpose"] = f"{grade.NO_RULE} Source: `{LIST}:3`"
        out.save(dest, "prose.json", prose)
        render.spec(dest)
        self.assertTrue(check(grade.run(dest), "rules-per-use-case")["pass"])

    def test_a_stated_reason_also_excuses_a_use_case(self):
        dest = self.mutated("r_reason", lambda t: t.replace(
            grade.NO_RULE, "No client-side rule: this use case only opens the assistant sheet."))
        self.assertTrue(check(grade.run(dest), "rules-per-use-case")["pass"])

    def test_a_placeholder_or_short_reason_does_not_excuse_a_use_case(self):
        for i, text in enumerate(("No client-side rule: <reason>.", "No client-side rule: none.")):
            dest = self.mutated(f"r_short{i}", lambda t, text=text: t.replace(grade.NO_RULE, text))
            self.assertFalse(check(grade.run(dest), "rules-per-use-case")["pass"], text)

    def test_a_contract_field_source_is_graded(self):
        dest = self.copy("f_source")
        data = out.load(dest, "endpoints.json")
        item = "Modules/PayslipsFeature/Sources/PayslipsFeature/PayslipItem.swift"
        data["endpoints"][0]["response"] = {"fields": [{"name": "gross", "type": "decimal", "required": False,
                                                        "nullable": "explicit", "source": f"{item}:3-70"}]}
        out.save(dest, "endpoints.json", data)
        render.spec(dest)
        c = check(grade.run(dest), "citations-resolve")
        self.assertFalse(c["pass"])
        self.assertIn(f"{item}:3-70", c["detail"])

    def test_criteria_per_use_case(self):
        dest = self.copy("c_gap")
        prose = out.load(dest, "prose.json")
        prose["criteria"] = prose["criteria"][:2]
        out.save(dest, "prose.json", prose)
        render.spec(dest)
        c = check(grade.run(dest), "criteria-per-use-case")
        self.assertFalse(c["pass"])
        self.assertIn("UC-003", c["detail"])

    def test_unknowns_have_owner(self):
        dest = self.mutated("u_owner", lambda t: t.replace("Is gross shown to part-timers?", "UNKNOWN: gross for part-timers")
                            .replace("Owner: payroll", "Contact: payroll"))
        c = check(grade.run(dest), "unknowns-have-owner")
        self.assertIn("UNKNOWN: gross for part-timers", c["detail"])
        self.assertFalse(c["pass"])
        fixed = self.mutated("u_ok", lambda t: t.replace("Is gross shown to part-timers? Searched: " + ITEM,
                                                         "UNKNOWN: gross for part-timers. Searched: " + ITEM))
        self.assertTrue(check(grade.run(fixed), "unknowns-have-owner")["pass"])

    def test_prose_complete_and_placeholders(self):
        dest = self.copy("p_missing")
        os.remove(os.path.join(dest, "prose.json"))
        render.spec(dest)
        result = grade.run(dest)
        c = check(result, "prose-complete")
        self.assertFalse(c["pass"])
        self.assertIn("UNKNOWN — summary not written yet", c["detail"])
        self.assertTrue(check(result, "unknowns-have-owner")["pass"])  # placeholders belong to prose-complete
        self.assertFalse(check(result, "criteria-per-use-case")["pass"])

    def test_no_duplicate_use_cases(self):
        def twice(text):
            row = next(l for l in text.splitlines() if l.startswith("| UC-001 |"))
            return text.replace(row, row + "\n" + row.replace("UC-001", "UC-009").replace("View payslip list", "view the Payslip list"))
        c = check(grade.run(self.mutated("dup", twice)), "no-duplicate-use-cases")
        self.assertFalse(c["pass"])
        self.assertIn("view the Payslip list", c["detail"])

    def test_citations_in_appendix_f_and_code_blocks_are_skipped(self):
        def add(text):
            return (text.replace("## Appendix F. Coverage", "```\n`Missing.swift:1`\n```\n\n## Appendix F. Coverage")
                    + "\n`Missing.swift:77`\n")
        self.assertTrue(check(grade.run(self.mutated("skip", add)), "citations-resolve")["pass"])
        c = check(grade.run(self.mutated("miss", lambda t: t.replace("## Open questions\n", "## Open questions\n\n`Missing.swift:2`\n"))),
                  "citations-resolve")
        self.assertFalse(c["pass"])
        self.assertIn("Missing.swift:2", c["detail"])

    def test_citation_in_a_contract_repository_resolves(self):
        dest = self.copy("contract")
        contract = os.path.join(self.tmp, "contract-repo")
        os.makedirs(os.path.join(contract, "src"), exist_ok=True)
        with open(os.path.join(contract, "src", "A.cs"), "w") as fh:
            fh.write("a\nb\nc\n")
        cfg = out.load_config(dest)
        cfg["contracts"] = [{"path": contract, "name": "me-api", "commit": "abc1234"}]
        out.save(dest, "app-spec.json", cfg)
        out.save_text(dest, "SPEC.md", read_text(self.good, "SPEC.md").replace("## Open questions\n", "## Open questions\n\n`src/A.cs:3`\n"))
        self.assertTrue(check(grade.run(dest), "citations-resolve")["pass"])
        out.save_text(dest, "SPEC.md", read_text(self.good, "SPEC.md").replace("## Open questions\n", "## Open questions\n\n`src/A.cs:4`\n"))
        self.assertFalse(check(grade.run(dest), "citations-resolve")["pass"])

    def test_banned_noun_in_a_path_or_code_span_is_not_a_requirement(self):
        dest = self.mutated("b_path", lambda t: t.replace("List the payslips of the year.",
                                                          "List the payslips; see `PayslipViewModel.swift` and ViewModelFactory.swift:3."))
        self.assertTrue(check(grade.run(dest), "banned-nouns")["pass"])
        whole = self.mutated("b_word", lambda t: t.replace("List the payslips of the year.", "List the payslips with a ViewModel."))
        self.assertFalse(check(grade.run(whole), "banned-nouns")["pass"])

    def test_detail_is_capped_at_twenty(self):
        def many(text):
            return text.replace("## Open questions\n", "## Open questions\n\n" + "\n".join(f"`X{i}.swift:1`" for i in range(25)) + "\n")
        c = check(grade.run(self.mutated("many", many)), "citations-resolve")
        self.assertIn("and 5 more", c["detail"])
        self.assertEqual(c["detail"].count("not found"), 20)


class TestCatalogCitations(GradeCase):
    """Every citation the renderer takes from a catalog is graded, backticked or not (the Design column, a screen's
    Source line and the Source column of Appendix A keep their bare text format)."""

    GHOST = "Modules/Invented/Ghost.swift:999"

    def rendered(self, name, catalog, change):
        dest = self.copy(name)
        edit(dest, catalog, change)
        render.spec(dest)
        return dest

    def failing_cites(self, dest):
        c = check(grade.run(dest), "citations-resolve")
        return c["pass"], c["detail"]

    def test_an_invented_file_in_a_use_case_fails_through_the_design_column(self):
        dest = self.rendered("design_ghost", "use-cases.json",
                             lambda d: d["useCases"][0].update(files=[self.GHOST]))
        self.assertIn(f"carry-as-is (ios-app {self.GHOST})", read_text(dest, "SPEC.md"))
        passed, detail = self.failing_cites(dest)
        self.assertFalse(passed)
        self.assertIn(f"{self.GHOST} (line ", detail)
        self.assertIn("file not found", detail)

    def test_a_design_line_beyond_the_file_fails(self):
        dest = self.rendered("design_long", "use-cases.json", lambda d: d["useCases"][0].update(files=[f"{LIST}:9999"]))
        passed, detail = self.failing_cites(dest)
        self.assertFalse(passed)
        self.assertIn(f"{LIST}:9999", detail)
        self.assertIn("the file has", detail)

    def test_a_design_file_without_a_line_must_exist(self):
        dest = self.rendered("design_noline", "use-cases.json",
                             lambda d: d["useCases"][0].update(files=["Modules/Invented/Ghost.swift"], screens=[]))
        self.assertIn("carry-as-is (ios-app Modules/Invented/Ghost.swift, line not resolved)", read_text(dest, "SPEC.md"))
        passed, detail = self.failing_cites(dest)
        self.assertFalse(passed)
        self.assertIn("Modules/Invented/Ghost.swift", detail)

    def test_an_invented_screen_declaration_fails_through_the_source_line(self):
        dest = self.rendered("screen_ghost", "screens.json", lambda d: d["screens"][0].update(file=self.GHOST))
        self.assertIn(f"- **Source:** {self.GHOST}", read_text(dest, "SPEC.md"))
        passed, detail = self.failing_cites(dest)
        self.assertFalse(passed)
        self.assertIn(self.GHOST, detail)

    def test_an_invented_element_fails_through_appendix_a(self):
        def change(d):
            d["screens"][0]["elements"][0].update(file="Modules/Invented/Ghost.swift", line=999)
        dest = self.rendered("element_ghost", "screens.json", change)
        passed, detail = self.failing_cites(dest)
        self.assertFalse(passed)
        self.assertIn(self.GHOST, detail)

    def test_the_good_spec_still_resolves_every_bare_citation(self):
        self.assertTrue(check(grade.run(self.good), "citations-resolve")["pass"])


class TestOverrides(GradeCase):
    def with_overrides(self, name, data, edit_catalog=None):
        dest = self.copy(name)
        write_overrides(dest, data)
        if edit_catalog:
            edit_catalog(dest)
        render.spec(dest)
        return dest

    def test_a_reflected_drop_passes_and_a_stale_spec_fails(self):
        drops = {"drop": [{"kind": "field", "id": "SCR-001.title", "reason": "not user-facing"},
                          {"kind": "screen", "id": "SCR-002", "reason": "out of module"},
                          {"kind": "string", "id": "payslip.list.title", "reason": "dead code"}]}
        dest = self.with_overrides("drop_ok", drops)
        self.assertTrue(check(grade.run(dest), "overrides-reflected")["pass"], check(grade.run(dest), "overrides-reflected"))
        stale = self.copy("drop_stale")
        write_overrides(stale, {"drop": [{"kind": "screen", "id": "SCR-002", "reason": "out of module"}]})
        c = check(grade.run(stale), "overrides-reflected")
        self.assertFalse(c["pass"])
        self.assertIn("SCR-002", c["detail"])
        self.assertIn("still in the spec", c["detail"])
        self.assertIn("missing from Appendix F", c["detail"])

    def test_a_dropped_use_case_must_leave_the_body(self):
        dest = self.with_overrides("drop_uc", {"drop": [{"kind": "useCase", "id": "UC-003", "reason": "dead code"}]})
        self.assertTrue(check(grade.run(dest), "overrides-reflected")["pass"])
        back = self.mutated("drop_uc_back", lambda t: t)
        write_overrides(back, {"drop": [{"kind": "useCase", "id": "UC-003", "reason": "dead code"}]})
        c = check(grade.run(back), "overrides-reflected")
        self.assertIn("UC-003", c["detail"])

    def test_rename_applied_and_not_applied(self):
        new = "Read a payslip in detail"

        def rename(dest):
            edit(dest, "use-cases.json", lambda d: next(u for u in d["useCases"] if u["id"] == "UC-002").update(name=new))
        ok = self.with_overrides("rename_ok", {"rename": [{"id": "UC-002", "name": new}]}, rename)
        self.assertIn(new, read_text(ok, "SPEC.md"))
        self.assertTrue(check(grade.run(ok), "overrides-reflected")["pass"], check(grade.run(ok), "overrides-reflected"))
        stale = self.with_overrides("rename_stale", {"rename": [{"id": "UC-002", "name": new}]})  # catalog keeps the old name
        c = check(grade.run(stale), "overrides-reflected")
        self.assertFalse(c["pass"])
        self.assertIn("UC-002", c["detail"])
        self.assertIn(f"'{new}' is not in the spec", c["detail"])
        both = self.mutated("rename_both", lambda t: t)
        write_overrides(both, {"rename": [{"id": "UC-002", "name": new}]})
        out.save_text(both, "SPEC.md", read_text(ok, "SPEC.md").replace(
            "## Open questions\n", "## Open questions\n\nStill called View a payslip's details.\n"))
        c = check(grade.run(both), "overrides-reflected")
        self.assertIn("old name", c["detail"])

    def test_unknown_ids_of_every_kind_are_named(self):
        dest = self.copy("unknown_kinds")
        write_overrides(dest, {
            "drop": [{"kind": "screen", "id": "SCR-404", "reason": "x"}, {"kind": "endpoint", "id": "EP-404", "reason": "x"},
                     {"kind": "event", "id": "ghost_event", "reason": "x"}, {"kind": "banana", "id": "B-1", "reason": "x"}],
            "rename": [{"id": "UC-404", "name": "N"}], "ids": {"SCR-001.nothing": "a.b"},
            "merge": [{"into": "UC-405", "from": ["UC-406"]}]})
        detail = check(grade.run(dest), "overrides-reflected")["detail"]
        for token in ("SCR-404", "EP-404", "ghost_event", "banana", "UC-404", "SCR-001.nothing", "UC-405", "UC-406"):
            self.assertIn(token, detail)

    def test_known_ids_pass_unknown_kinds_do_not_hide_other_items(self):
        dest = self.copy("known_ids")
        write_overrides(dest, {"ids": {"SCR-001.title": "pay.list.title"}, "merge": []})
        self.assertTrue(check(grade.run(dest), "overrides-reflected")["pass"])


class TestFixRound1(GradeCase):
    def test_a_stale_dropped_string_in_appendix_a_fails(self):
        stale = self.mutated("string_stale", lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("| payslip.list.title |")))
        write_overrides(stale, {"drop": [{"kind": "string", "id": "payslip.list.title", "reason": "dead code"}]})
        c = check(grade.run(stale), "overrides-reflected")
        self.assertFalse(c["pass"])
        self.assertIn("payslip.list.title", c["detail"])
        self.assertIn("still in the spec", c["detail"])

    def test_slash_words_are_not_masked_for_banned_nouns(self):
        dest = self.mutated("slash", lambda t: t.replace("List the payslips of the year.", "Use Realm/Room and ViewModel/Presenter."))
        c = check(grade.run(dest), "banned-nouns")
        self.assertFalse(c["pass"])
        for noun in ("Realm", "Room", "ViewModel"):
            self.assertIn(noun, c["detail"])

    def test_rule_placeholder_exemption_is_anchored(self):
        hint = 'UNKNOWN — no rule extracted for UC-003; add a rule or write "No client-side rule; the server decides." or "No client-side rule: <reason>." with a citation'
        screens = self.mutated("ph_screens", lambda t: t.replace("List the payslips of the year.", hint))
        self.assertFalse(check(grade.run(screens), "prose-complete")["pass"])
        fake = self.mutated("ph_fake", lambda t: t.replace("## Dependencies and decisions\n",
                                                           "## Dependencies and decisions\n\nUNKNOWN — no rule extracted for UC-999; add\n"))
        self.assertFalse(check(grade.run(fake), "prose-complete")["pass"])
        inside = self.mutated("ph_inside", lambda t: t.replace("### Permissions", hint + "\n\n### Permissions"))
        self.assertTrue(check(grade.run(inside), "prose-complete")["pass"])
        glued = self.mutated("ph_glued", lambda t: t.replace("### Permissions", "Note: " + hint + " and more\n\n### Permissions"))
        self.assertFalse(check(grade.run(glued), "prose-complete")["pass"])

    def test_renderer_and_grader_agree_on_use_cases_without_a_rule(self):
        """UC-003 carries the cited no-rule sentence in its criterion: neither the renderer nor the grader lists it."""
        text = read_text(self.good, "SPEC.md")
        self.assertNotIn("no rule extracted for", text)
        self.assertTrue(check(grade.run(self.good), "rules-per-use-case")["pass"])
        dest = self.copy("no_rule_uncited")

        def uncite(p):
            p["criteria"][2]["evidence"] = ""
        edit(dest, "prose.json", uncite)
        text = render.spec(dest)
        self.assertIn("no rule extracted for UC-003;", text)
        c = check(grade.run(dest), "rules-per-use-case")
        self.assertFalse(c["pass"])
        self.assertIn("UC-003", c["detail"])

    def test_a_bare_citation_does_not_satisfy_the_no_rule_sentence(self):
        dest = self.mutated("bare", lambda t: t.replace(f"`{LIST}:12`", f"{LIST}:12"))
        c = check(grade.run(dest), "rules-per-use-case")
        self.assertFalse(c["pass"])
        self.assertIn("UC-003", c["detail"])

    def test_host_with_a_port_is_not_a_citation(self):
        dest = self.mutated("host", lambda t: t.replace("## Open questions\n", "## Open questions\n\nCalls `api.visma.net:443` and `localhost:8080`.\n"))
        self.assertTrue(check(grade.run(dest), "citations-resolve")["pass"])
        for text in ("`api/visma.yml:2`", "`Missing.xcstrings:2`", "`a/b:3`"):
            dest = self.mutated("src", lambda t: t.replace("## Open questions\n", "## Open questions\n\n" + text + "\n"))
            self.assertFalse(check(grade.run(dest), "citations-resolve")["pass"], text)


class TestCli(GradeCase):
    def test_exit_codes_and_output(self):
        code, stdout, err = run_cli(["grade.py", self.good], module=grade)
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Grade: pass", stdout)
        bad = self.mutated("cli_bad", lambda t: t.replace(f"`{LIST}:12`", f"`{LIST}:9999`", 1))
        code, stdout, _ = run_cli(["grade.py", bad], module=grade)
        self.assertEqual(code, 1)
        self.assertIn("FAIL citations-resolve", stdout)
        self.assertIn(":9999", stdout)

    def test_bad_folder_and_bad_arguments_exit_2(self):
        code, _, err = run_cli(["grade.py", os.path.join(self.tmp, "nowhere")], module=grade)
        self.assertEqual(code, 2)
        self.assertIn("not an app-spec output folder", err)
        self.assertEqual(run_cli(["grade.py"], module=grade)[0], 2)
        self.assertEqual(run_cli(["grade.py", self.good, "--name"], module=grade)[0], 2)
        self.assertEqual(run_cli(["grade.py", self.good, "--name", "../x.md"], module=grade)[0], 2)
        self.assertEqual(run_cli(["grade.py", self.good, "--name", "missing.md"], module=grade)[0], 2)

    def test_name_grades_another_file(self):
        dest = self.copy("named")
        render.spec(dest, "docs/payslips.md")
        code, stdout, err = run_cli(["grade.py", dest, "--name", "docs/payslips.md"], module=grade)
        self.assertEqual(code, 0, stdout + err)
        out.save_text(dest, "docs/payslips.md", "# nothing\n")
        self.assertEqual(run_cli(["grade.py", dest, "--name", "docs/payslips.md"], module=grade)[0], 1)
        self.assertEqual(run_cli(["grade.py", dest], module=grade)[0], 0)  # SPEC.md is untouched


if __name__ == "__main__":
    unittest.main()
