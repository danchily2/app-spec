#!/usr/bin/env python3
"""The review files of an output folder: the scorecard, the open questions and accepted gaps.

    python3 review.py reset <out>
    python3 review.py append <out> --critic FILE
    python3 review.py questions <out>
    python3 review.py uncovered <out>
    python3 review.py accept <out> --kind KIND --id ID --reason TEXT

`reset` deletes review.json and REVIEW.md: the spec skill runs it at the start of every run.

`append` adds one pass to review.json, `{"n", "ledger": {"pass"}, "grade": {"pass"}, "critic": [findings]}`, with the
verdicts of the current ledger.json and grade.json and the critic's findings from FILE (a JSON list of
`{"severity", "section", "finding", "fix", "owner"}`; an entry without a known severity or owner is reported and left
out). The appendices that are not prose are routed by section: an Appendix F finding (a coverage reason) goes to
`person`, and an Appendix A finding (a field row) sent to `writer` goes to `analyst`. It then writes REVIEW.md from review.json: the scorecard of every pass, the findings that remain after the last
pass, and the failing ledger classes and grade checks.

`questions` writes OPEN_QUESTIONS.md with the entries, ids and order of the spec's section 8: the open questions of
prose.json, then one `OQ-NNN` per endpoint the catalog leaves incomplete and one per rule below High confidence, each
with what was searched and who can answer.

`uncovered` prints, as JSON, every item ledger.json lists as uncovered without a reason, with the override `kind` and
`id` that `accept` records for it. `accept` adds `{"kind", "id", "reason"}` to the `drop` list of overrides.json, or
replaces the reason of the same kind and id. It never removes anything else from overrides.json.

Exit code 2 when `<out>` is not an output folder or an input file is missing or not valid. Standard library only.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out, spec_md  # noqa: E402
from speclib.common import die, load_json  # noqa: E402

SEVERITIES = ("Blocker", "High", "Medium", "Nit")
OWNERS = ("analyst", "mapper", "rules", "contracts", "writer", "person")
AGENTS = OWNERS[:-1]  # the owners the spec skill sends a finding to; a `person` finding waits for a person
KIND = {"screens": "screen", "fields": "field", "endpoints": "endpoint", "strings": "string", "events": "event",
        "storage": "storage", "permissions": "permission", "platform": "platform"}
KINDS = ("field", "screen", "useCase", "endpoint", "string", "event", "storage", "permission", "platform")


def _cell(value):
    return " ".join(str(value if value is not None else "").split()).replace("|", "\\|")


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- reset, append, REVIEW.md


def reset(dest):
    for name in ("review.json", "REVIEW.md"):
        path = os.path.join(dest, name)
        if os.path.isfile(path):
            os.remove(path)


def findings(path):
    """The valid findings in the critic's JSON file `path`, and the number left out."""
    data = load_json(path, None)
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        data = data["findings"]
    if not isinstance(data, list):
        die(f"{path} is not a JSON list of critic findings")
    kept, skipped = [], 0
    for f in data:
        if (isinstance(f, dict) and f.get("severity") in SEVERITIES and f.get("owner") in OWNERS
                and isinstance(f.get("finding"), str) and f["finding"].strip()):
            kept.append(_route({k: f.get(k) for k in ("severity", "section", "finding", "fix", "owner")}))
        else:
            skipped += 1
    return kept, skipped


def _route(finding):
    """The finding with the owner that can fix its section: no agent writes Appendix F, the writer never Appendix A."""
    section = str(finding.get("section") or "")
    if section.startswith("Appendix F"):
        finding["owner"] = "person"
    elif section.startswith("Appendix A") and finding["owner"] == "writer":
        finding["owner"] = "analyst"
    return finding


def for_agents(critic):
    """The Blocker and High findings the spec skill sends back to an agent: every owner but `person`."""
    return [f for f in critic if f.get("severity") in ("Blocker", "High") and f.get("owner") in AGENTS]


def append(dest, critic):
    doc = _dict(out.load(dest, "review.json", {}))
    passes = [p for p in _list(doc.get("passes")) if isinstance(p, dict)]
    ledger, grade = _dict(out.load(dest, "ledger.json", {})), _dict(out.load(dest, "grade.json", {}))
    passes.append({"n": len(passes) + 1, "ledger": {"pass": ledger.get("pass") is True},
                   "grade": {"pass": grade.get("pass") is True}, "critic": critic})
    doc = {"passes": passes}
    out.save(dest, "review.json", doc)
    out.save_text(dest, "REVIEW.md", render_review(dest, doc))
    return doc


def render_review(dest, doc):
    cfg = out.load_config(dest)
    options = _dict(cfg.get("options"))
    passes = doc["passes"]
    last = passes[-1] if passes else {"critic": []}
    lines = ["# Review", "", f"Spec: `{options.get('specName') or 'SPEC.md'}`. Passes run: {len(passes)} of at most "
             f"{options.get('passes') or 2}. Blocker and High findings go back to their owner between passes.", "",
             "| Pass | Ledger | Grade | Blocker | High | Medium | Nit |", "|---|---|---|---|---|---|---|"]
    for p in passes:
        counts = [sum(1 for f in p["critic"] if f.get("severity") == s) for s in SEVERITIES]
        lines.append("| " + " | ".join(str(v) for v in [p["n"], "pass" if p["ledger"]["pass"] else "fail",
                                                        "pass" if p["grade"]["pass"] else "fail", *counts]) + " |")
    lines += ["", f"## Findings that remain after pass {last.get('n', 0)}", ""]
    remaining = sorted((f for f in last["critic"] if f.get("owner") != "person"), key=lambda f: SEVERITIES.index(f["severity"]))
    lines += [f"- **{f['severity']}, {_cell(f.get('section')) or 'section not named'}** (owner: {f['owner']}): "
              f"{_cell(f['finding'])} Fix: {_cell(f.get('fix')) or 'not given'}" for f in remaining] or ["None."]
    decide = sorted((f for f in last["critic"] if f.get("owner") == "person"), key=lambda f: SEVERITIES.index(f["severity"]))
    if decide:
        lines += ["", "## For a person to decide", "",
                  "No agent can settle these. Record a reason with `review.py accept OUT --kind KIND --id ID --reason "
                  "TEXT`, or change `overrides.json`.", ""]
        lines += [f"- **{f['severity']}, {_cell(f.get('section')) or 'section not named'}:** {_cell(f['finding'])} "
                  f"Fix: {_cell(f.get('fix')) or 'not given'}" for f in decide]
    ledger, grade = _dict(out.load(dest, "ledger.json", {})), _dict(out.load(dest, "grade.json", {}))
    failing = [f"- Ledger, {name}: {c.get('percent')} percent of {_dict(ledger.get('thresholds')).get(name)} percent"
               for name, c in _dict(ledger.get("classes")).items() if isinstance(c, dict) and c.get("pass") is False]
    failing += [f"- Grade, {_cell(c.get('name'))}: {_cell(c.get('detail'))}"
                for c in _list(grade.get("checks")) if isinstance(c, dict) and c.get("pass") is False]
    lines += ["", "## Checks that fail now", ""] + (failing or ["None."])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- OPEN_QUESTIONS.md


def questions(dest):
    """Write OPEN_QUESTIONS.md from the same entries, ids and order as section 8 of the spec."""
    cfg = out.load_config(dest)
    rows = [[q["id"], q["question"], q["searched"], q["owner"]] for q in spec_md.open_question_entries(spec_md.Context(dest))]
    module = " ".join(_list(_dict(cfg.get("module")).get("query"))) or "unknown"
    lines = ["# Open questions", "", f"Module {module} of {_dict(cfg.get('app')).get('name')}. Every UNKNOWN of the spec, "
             "with what was searched and who can answer.", ""]
    if rows:
        lines += ["| Id | Question | Searched | Owner |", "|---|---|---|---|"]
        lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    else:
        lines.append("None recorded.")
    out.save_text(dest, "OPEN_QUESTIONS.md", "\n".join(lines) + "\n")
    return rows


# ---------------------------------------------------------------- uncovered items and accept


def uncovered(dest):
    ledger = out.load(dest, "ledger.json")
    if not isinstance(ledger, dict):
        die(f"{dest} has no ledger.json (run ledger.py first)")
    eps = {f"{str(e.get('method') or '').upper()} {e.get('path')}": e["id"]
           for e in _list(_dict(out.load(dest, "endpoints.json", {})).get("endpoints")) if isinstance(e, dict) and e.get("id")}
    items = []
    for name, cls in _dict(ledger.get("classes")).items():
        for u in _list(_dict(cls).get("uncovered")):
            if isinstance(u, dict) and not u.get("reason") and name in KIND:
                item = str(u.get("item"))
                ident = eps.get(item, item) if name == "endpoints" else item
                items.append({"class": name, "kind": KIND[name], "id": ident, "item": item})
    return items


def accept(dest, kind, ident, reason):
    if kind not in KINDS:
        die(f"--kind must be one of {', '.join(KINDS)}")
    if not reason.strip():
        die("--reason must not be empty")
    doc = out.load(dest, "overrides.json", None)
    if doc is None:
        doc = {"version": 1, "drop": [], "rename": [], "ids": {}, "merge": []}
    if not isinstance(doc, dict):
        die(f"{dest}/overrides.json is not a JSON object; fix it by hand first")
    drops = doc.setdefault("drop", [])
    entry = next((d for d in drops if isinstance(d, dict) and d.get("kind") == kind and str(d.get("id")) == ident), None)
    if entry:
        entry["reason"] = reason.strip()
    else:
        drops.append({"kind": kind, "id": ident, "reason": reason.strip()})
    out.save(dest, "overrides.json", doc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("reset", "questions", "uncovered"):
        sub.add_parser(name).add_argument("out")
    ap_append = sub.add_parser("append")
    ap_append.add_argument("out")
    ap_append.add_argument("--critic", required=True, metavar="FILE")
    ap_accept = sub.add_parser("accept")
    ap_accept.add_argument("out")
    ap_accept.add_argument("--kind", required=True)
    ap_accept.add_argument("--id", required=True)
    ap_accept.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    out.load_config(args.out)
    if args.command == "reset":
        reset(args.out)
        print(f"Removed review.json and REVIEW.md from {args.out}")
    elif args.command == "append":
        kept, skipped = findings(args.critic)
        doc = append(args.out, kept)
        p = doc["passes"][-1]
        print(f"Pass {p['n']}: ledger {'pass' if p['ledger']['pass'] else 'fail'}, grade "
              f"{'pass' if p['grade']['pass'] else 'fail'}, "
              + ", ".join(f"{sum(1 for f in kept if f['severity'] == s)} {s}" for s in SEVERITIES))
        if skipped:
            print(f"{skipped} finding(s) left out: no known severity, no known owner or no finding text", file=sys.stderr)
        print(f"Wrote {args.out}: review.json, REVIEW.md")
    elif args.command == "questions":
        rows = questions(args.out)
        print(f"Wrote {args.out}: OPEN_QUESTIONS.md ({len(rows)} questions)")
    elif args.command == "uncovered":
        print(json.dumps(uncovered(args.out), indent=2, ensure_ascii=False))
    else:
        accept(args.out, args.kind, args.id, args.reason)
        print(f"Recorded in {args.out}/overrides.json: drop {args.kind} {args.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
