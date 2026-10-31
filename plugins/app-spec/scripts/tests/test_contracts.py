import os
import shutil
import tempfile
import unittest

from helpers import FIX, run_cli
from speclib import out
from test_render_catalogs import build_out

import contracts
import render

ASPNET = str(FIX / "backend-aspnet")
EXPRESS = str(FIX / "backend-express")
EMPTY = str(FIX / "backend-empty")


class TestLocateRoutes(unittest.TestCase):
    def test_aspnet_route_joins_prefix_and_policy(self):
        routes = contracts.locate_routes(ASPNET, "aspnet")
        r = next(x for x in routes if x["method"] == "GET" and x["path"].endswith("/employees/{odpUserId}/payslips"))
        self.assertEqual(r["auth"], "PayslipUsersReadPolicy")
        self.assertTrue(r["file"].endswith("PayslipController.cs"))
        self.assertEqual(r["path"], "/employee/api/v1/employees/{odpUserId}/payslips")
        self.assertEqual(r["responseType"], "PayslipListDto")
        self.assertEqual(r["requestType"], "PayslipQuery")
        self.assertEqual(r["line"], 11)

    def test_aspnet_absolute_template_and_bare_authorize(self):
        routes = contracts.locate_routes(ASPNET, "aspnet")
        r = next(x for x in routes if x["method"] == "POST")
        self.assertEqual(r["path"], "/employee/api/v1/payslips/{payslipId}/acknowledge")
        self.assertEqual(r["auth"], "Authorize")
        self.assertEqual(r["responseType"], "AckDto")

    def test_aspnet_controller_token_and_empty_action_template(self):
        paths = {(x["method"], x["path"]) for x in contracts.locate_routes(ASPNET, "aspnet")}
        self.assertIn(("GET", "/api/v1/Ping"), paths)
        self.assertIn(("DELETE", "/api/v1/Ping/{id}"), paths)

    def test_express_route(self):
        self.assertIn(("GET", "/employees/:id/payslips"),
                      {(r["method"], r["path"]) for r in contracts.locate_routes(EXPRESS, "express")})

    def test_express_double_quotes_and_nest_controller(self):
        paths = {(r["method"], r["path"]) for r in contracts.locate_routes(EXPRESS, "express")}
        self.assertIn(("POST", "/employees/:id/payslips/refresh"), paths)
        self.assertIn(("GET", "/employee/api/v1/reports/:reportId"), paths)
        self.assertIn(("POST", "/employee/api/v1/reports"), paths)

    def test_detect_framework(self):
        self.assertEqual(contracts.detect_framework(ASPNET), "aspnet")
        self.assertEqual(contracts.detect_framework(EXPRESS), "express")
        self.assertEqual(contracts.detect_framework(EMPTY), "unknown")

    def test_unknown_framework_finds_nothing(self):
        self.assertEqual(contracts.locate_routes(EMPTY, "unknown"), [])


class TestEnrich(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = build_out(self.tmp, "o")
        render.catalogs(self.out)

    def tearDown(self):
        shutil.rmtree(self.tmp, True)

    def eps(self):
        return out.load(self.out, "endpoints.json")["endpoints"]

    def payslips(self):
        return next(e for e in self.eps() if e["path"].endswith("/payslips"))

    def pdf(self):
        return next(e for e in self.eps() if e["client"]["file"].endswith("GetPayslipPdf.swift"))

    def test_enrich_marks_verified_and_leaves_pdf_unmatched(self):
        contracts.enrich(self.out, ASPNET)
        e = self.payslips()
        self.assertEqual(e["label"], "VERIFIED")
        self.assertEqual(e["backend"]["repo"], "backend-aspnet")
        self.assertEqual(e["backend"]["file"], "Controllers/PayslipController.cs")
        self.assertEqual(e["backend"]["line"], 11)
        self.assertEqual(e["backend"]["auth"], "PayslipUsersReadPolicy")
        pdf = self.pdf()
        self.assertIsNone(pdf["backend"])
        self.assertEqual(pdf["label"], "UNKNOWN")

    def test_enrich_is_idempotent(self):
        contracts.enrich(self.out, ASPNET)
        first = self.eps()
        contracts.enrich(self.out, ASPNET)
        self.assertEqual(self.eps(), first)

    def test_second_repo_does_not_clear_a_match(self):
        contracts.enrich(self.out, ASPNET)
        first = self.eps()
        contracts.enrich(self.out, EMPTY)
        self.assertEqual(self.eps(), first)
        contracts.enrich(self.out, EXPRESS)
        self.assertEqual(self.payslips()["backend"]["repo"], "backend-aspnet")
        self.assertEqual(self.payslips()["label"], "VERIFIED")

    def test_express_repo_matches_too(self):
        contracts.enrich(self.out, EXPRESS)
        self.assertEqual(self.payslips()["backend"]["file"], "routes/payslips.ts")
        self.assertIsNone(self.payslips()["backend"]["auth"])
        self.assertEqual(self.payslips()["label"], "VERIFIED")

    def test_label_rules(self):
        eps = out.load(self.out, "endpoints.json")
        base = self.payslips()
        # matched but no citing use case -> INFERRED
        eps["endpoints"] = [dict(base, useCases=[], label="UNKNOWN")]
        out.save(self.out, "endpoints.json", eps)
        contracts.enrich(self.out, ASPNET)
        self.assertEqual(self.eps()[0]["label"], "INFERRED")
        # unmatched, was verified from the client -> INFERRED
        eps["endpoints"] = [dict(base, path="/employee/api/v1/nothing/here", backend=None, label="VERIFIED")]
        out.save(self.out, "endpoints.json", eps)
        contracts.enrich(self.out, ASPNET)
        self.assertEqual((self.eps()[0]["label"], self.eps()[0]["backend"]), ("INFERRED", None))
        # unmatched UNKNOWN stays UNKNOWN
        eps["endpoints"] = [dict(base, path="/employee/api/v1/{}", backend=None, label="UNKNOWN")]
        out.save(self.out, "endpoints.json", eps)
        contracts.enrich(self.out, ASPNET)
        self.assertEqual(self.eps()[0]["label"], "UNKNOWN")

    def _repo(self, routes):
        """An express repo with one file per (name, [paths]) pair."""
        repo = os.path.join(self.tmp, "repo%d" % len(os.listdir(self.tmp)))
        os.makedirs(os.path.join(repo, "routes"))
        for name, paths in routes.items():
            with open(os.path.join(repo, "routes", name + ".ts"), "w") as fh:
                fh.write("import express from 'express';\nconst router = express.Router();\n")
                fh.writelines(f"router.get('{p}', h);\n" for p in paths)
        return repo

    def _one(self, path, repo):
        base = getattr(self, "_base", None) or self.payslips()
        self._base = base
        out.save(self.out, "endpoints.json", {"version": 1, "endpoints": [dict(base, path=path, backend=None)]})
        contracts.enrich(self.out, repo)
        return self.eps()[0]

    def test_more_agreeing_literals_win_at_equal_length(self):
        # each route alone matches; both are one segment longer, b agrees on one more literal from the end
        alone = self._one("/v1/payslips/{}/lines", self._repo({"a": ["/api/:v/payslips/:id/lines"]}))
        self.assertEqual(alone["backend"]["file"], "routes/a.ts")
        repo = self._repo({"a": ["/api/:v/payslips/:id/lines"], "b": ["/api/v1/payslips/:id/lines"]})
        e = self._one("/v1/payslips/{}/lines", repo)
        self.assertEqual(e["backend"]["file"], "routes/b.ts")  # file order alone would pick routes/a.ts
        self.assertNotIn("disagreements", e)

    def test_closer_segment_count_wins_without_exact_match(self):
        repo = self._repo({"a": ["/api/v1/payslips/:id"], "b": ["/admin/payslips/:id"]})
        e = self._one("/payslips/{}", repo)
        self.assertEqual(e["backend"]["file"], "routes/b.ts")

    def test_exact_route_wins_over_longer_tail_match(self):
        repo = self._repo({"a": ["/admin/payslips/:id"], "b": ["/payslips/:id"]})
        e = self._one("/payslips/{}", repo)
        self.assertEqual(e["backend"]["file"], "routes/b.ts")

    def test_parameter_route_preferred_over_literal(self):
        repo = self._repo({"a": ["/employees/me/payslips"], "b": ["/employees/:id/payslips"]})
        e = self._one("/employees/{}/payslips", repo)
        self.assertEqual(e["backend"]["file"], "routes/b.ts")

    def test_equal_routes_in_two_files_are_ambiguous(self):
        repo = self._repo({"a": ["/admin/payslips/:id"], "b": ["/staff/payslips/:id"]})
        e = self._one("/payslips/{}", repo)
        self.assertIsNone(e["backend"])
        self.assertEqual(e["label"], "INFERRED")
        d = e["disagreements"]
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["field"], d[0]["note"]), ("route", "ambiguous backend route"))
        self.assertIn("routes/a.ts:3 | routes/b.ts:3", d[0]["backend"])
        contracts.enrich(self.out, repo)
        self.assertEqual(self.eps()[0]["disagreements"], d)

    def test_cli(self):
        code, _, err = run_cli(["contracts.py", self.out, "--repo", ASPNET, "--framework", "aspnet"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.payslips()["label"], "VERIFIED")

    def test_cli_uses_configured_contracts(self):
        cfg = out.load_config(self.out)
        cfg["contracts"] = [{"path": ASPNET, "name": "me-api", "commit": None}]
        out.save(self.out, "app-spec.json", cfg)
        code, _, err = run_cli(["contracts.py", self.out])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.payslips()["backend"]["repo"], "me-api")  # the configured name, never the path

    def test_backend_repo_is_a_name_and_the_spec_has_no_home_path(self):
        contracts.enrich(self.out, ASPNET)
        render.spec(self.out)
        with open(os.path.join(self.out, "SPEC.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn(ASPNET, text)
        self.assertIn("- **Backend:** backend-aspnet `Controllers/PayslipController.cs:11`", text)


if __name__ == "__main__":
    unittest.main()
