#!/usr/bin/env python3
"""Check the shape of the spec: headings, criteria, citations, unknowns, banned nouns and the overrides.

    python3 grade.py <out> [--name FILE]

Reads the spec (`SPEC.md`, or `FILE` inside the output folder `<out>`), the catalogs, `overrides.json`,
`inventory.json` and `app-spec.json`, and writes `grade.json`:

    {"version": 1, "checks": [{"name", "pass", "detail"}], "pass": bool}

`citations-resolve` checks every backticked `path:line` outside Appendix F and code blocks, and every location the
renderer writes bare from a catalog: the Design column of section 2, a screen's Source line and the Source column of
Appendix A. Each must lie in a file under the app root or a contract root, within its line count.

The checks, in this order: sections, rules-per-use-case, criteria-per-use-case, criteria-numbering, citations-resolve,
unknowns-have-owner, prose-complete, no-duplicate-use-cases, banned-nouns, overrides-reflected. `detail` names every
failing item, at most 20, then `and N more`. Nothing here judges whether a sentence is true: that is the critic's job.

Exit code 0 when every check passes, 1 when one fails, 2 when `<out>` is not an output folder or a catalog is missing.
Standard library only; analysed code is read, never executed or written.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ledger import _Ledger, _platform_values  # noqa: E402
from speclib import out, paths  # noqa: E402
from speclib.common import die  # noqa: E402
from speclib.ids import norm  # noqa: E402
from speclib.spec_md import NO_RULE, NO_RULE_RE, NO_RULE_REASON, OUT_OF_SCOPE_LEAD, Context, _element_rows, target  # noqa: E402
from speclib.template import APPENDICES, AC_RE, CITE_RE, HEADINGS  # noqa: E402

CHECKS = ("sections", "rules-per-use-case", "criteria-per-use-case", "criteria-numbering", "citations-resolve",
          "unknowns-have-owner", "prose-complete", "no-duplicate-use-cases", "banned-nouns", "overrides-reflected")
MAX_DETAIL = 20

BODY = HEADINGS                                            # sections 1 to 8
NOT_COVERAGE = HEADINGS + APPENDICES[:5]                   # everything the spec says except the coverage appendix
APPENDIX_F = APPENDICES[5]

_SPAN = re.compile(r"`([^`\n]+)`")
_CITE = re.compile(r"^(\S+?):(\d+)(?:-(\d+))?$")
_CITE_SHAPE = re.compile(r"(?<![\w@+.\-/])" + CITE_RE + r"(?![\w])")  # a citation-shaped token, backticked or not
_CITE_FULL = re.compile("^" + CITE_RE + "$")
_PLACEHOLDER = "UNKNOWN — "
_NO_RULES_LINE = "UNKNOWN — no rules extracted"  # the renderer's two own lines; rules-per-use-case judges them
_NO_RULE_LINE = re.compile(r"^UNKNOWN — no rule extracted for ((?:UC|CAP)-\d{3,}(?:, (?:UC|CAP)-\d{3,})*); add a rule or write "
                           r'"' + re.escape(NO_RULE) + r'" or "' + re.escape(NO_RULE_REASON) + r'" with a citation$')
_ROW_SPLIT = re.compile(r"(?<!\\)\|")
_OQ_REF = re.compile(r"\bopen question (OQ-\d{3,})\b")
_OQ_ITEM = re.compile(r"^- \*\*(OQ-\d{3,}):\*\* .*\bSearched: .*\bOwner: ")


# ---------------------------------------------------------------- the spec as lines with a section

class _Spec:
    def __init__(self, text):
        self.rows = []  # (line number, text, in a code block, heading of its section or None before the first heading)
        section, fenced = None, False
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                self.rows.append((number, line, True, section))
                fenced = not fenced
                continue
            if not fenced and line.startswith("## "):
                section = line.rstrip()
                self.rows.append((number, line, False, section))
                continue
            self.rows.append((number, line, fenced, section))
        self.headings = [t for _, t, code, sec in self.rows if not code and t.startswith("## ") and t.rstrip() == sec]

    def lines(self, headings, code=False):
        """`(number, text)` of the lines under the given headings, code blocks left out unless `code`."""
        want = set(headings)
        return [(n, t) for n, t, c, s in self.rows if s in want and not t.startswith("## ") and (code or not c)]

    def text(self, headings, code=True):
        return "\n".join(t for _, t in self.lines(headings, code))


def _detail(items):
    items = list(dict.fromkeys(items))
    shown = "; ".join(items[:MAX_DETAIL])
    return shown + (f"; and {len(items) - MAX_DETAIL} more" if len(items) > MAX_DETAIL else "")


def _token(ident):
    """A regex for `ident` as a whole token: not inside a longer id, key or name."""
    return re.compile(r"(?<![\w-])(?<!\w\.)" + re.escape(str(ident)) + r"(?![\w-]|\.\w)")


def _unmarked(line):
    """`line` without the parts that name code: backticked spans, paths and citations."""
    line = _SPAN.sub(" ", line)
    return _CITE_SHAPE.sub(" ", line)


def _has_citation(line):
    return any(_cites(line))


def _cites(line):
    """Each `(text, path, first line, last line)` of a backticked `path:line` or `path:line-line` on `line`."""
    for span in _SPAN.finditer(line):
        for part in re.split(r"\s*[,;]\s*", span.group(1).strip()):
            m = _CITE.match(part)
            if m and _CITE_FULL.match(part):
                yield part, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))


# ---------------------------------------------------------------- the grader

class _Grader:
    def __init__(self, dest, name):
        self.dest = dest
        self.ctx = Context(dest)  # exits 2 when the output folder or a catalog is missing
        path = os.path.join(dest, target(dest, name))
        if not os.path.isfile(path):
            die(f"{path} not found (run render.py spec first)")
        with open(path, encoding="utf-8") as fh:
            self.spec = _Spec(fh.read())
        self.cfg = self.ctx.cfg
        self.roots = [str(self.cfg["app"]["path"])] + [str(c["path"]) for c in self.cfg.get("contracts") or []
                                                       if isinstance(c, dict) and c.get("path")]
        self._lengths = {}

    # ------------------------------------------------------------ sections

    def sections(self):
        expected, found = HEADINGS + APPENDICES, self.spec.headings
        items = [f"missing {h}" for h in expected if h not in found]
        items += [f"unexpected {h}" for h in found if h not in expected]
        items += [f"repeated {h}" for h in dict.fromkeys(found) if found.count(h) > 1]
        known = [h for h in dict.fromkeys(found) if h in expected]
        if not items and known != [h for h in expected if h in known]:
            items.append("headings out of order: " + ", ".join(h[3:] for h in known))
        return items

    # ------------------------------------------------------------ use cases

    def _shown_ids(self, case):
        return {case["id"], self.ctx.shown[case["id"]]}

    def _label(self, case):
        return f"{self.ctx.shown[case['id']]} {case['name']}"

    def _ac_lines(self):
        """`(number, text, ids)` of every acceptance-criterion line of section 6."""
        found = []
        for number, text in self.spec.lines([HEADINGS[5]]):
            m = re.match(r"^- \*\*AC\d+ \(([^)]*)\):\*\*", text)
            if m:
                found.append((number, text, {i.strip() for i in m.group(1).split(",")}))
        return found

    def rules_per_use_case(self):
        ruled = {r.get("useCase") for r in self.ctx.rules}
        screens = self.spec.lines([HEADINGS[2]])
        acs = self._ac_lines()
        items = []
        for case in self.ctx.cases:
            if case["id"] in ruled:
                continue
            sentence = [t for _, t in self._screen_section_lines(screens, case)]
            sentence += [t for _, t, ids in acs if ids & self._shown_ids(case)]
            if not any(NO_RULE_RE.search(t) and _has_citation(t) for t in sentence):
                items.append(f"{self._label(case)} has no rule and no cited sentence '{NO_RULE}' or '{NO_RULE_REASON}'")
        return items

    def _screen_section_lines(self, screens, case):
        """The lines of the `###` blocks of the screens of `case` in the Screens section."""
        ids = {s for s in case.get("screens") or []}
        ids |= {s["id"] for s in self.ctx.screens if case["id"] in (s.get("useCases") or [])}
        picked, inside = [], False
        for number, text in screens:
            if text.startswith("### "):
                inside = any(f"({s})" in text for s in ids)
            if inside:
                picked.append((number, text))
        return picked

    def criteria_per_use_case(self):
        acs = [(ids, t) for _, t, ids in self._ac_lines() if _PLACEHOLDER not in t]
        covered = set().union(*[ids for ids, _ in acs]) if acs else set()
        return [f"{self._label(c)} has no acceptance criterion" for c in self.ctx.cases
                if not (self._shown_ids(c) & covered)]

    def criteria_numbering(self):
        items, numbers = [], []
        pattern = re.compile(AC_RE)
        for number, text in self.spec.lines([HEADINGS[5]]):
            if not text.startswith("- **AC"):
                continue
            m = pattern.match(text)
            if not m:
                items.append(f"line {number} is not an AC line: {text[:60]}")
            else:
                numbers.append((number, int(m.group(1))))
        for position, (number, n) in enumerate(numbers, 1):
            if n != position:
                items.append(f"line {number} is AC{n}, expected AC{position}")
                break
        return items

    def no_duplicate_use_cases(self):
        names = []
        rows = [t for _, t in self.spec.lines([HEADINGS[1]]) if t.startswith("|")]
        for row in rows[2:]:  # the head and the separator
            cells = [c.strip() for c in _ROW_SPLIT.split(row.strip().strip("|"))]
            if len(cells) > 1:
                names.append(cells[1])
        names = names or [c["name"] for c in self.ctx.cases]
        seen, items = {}, []
        for name in names:
            key = norm(name)
            if key in seen:
                items.append(f"'{name}' repeats '{seen[key]}'")
            seen.setdefault(key, name)
        return items

    # ------------------------------------------------------------ citations

    def _by_name(self):
        """{file name: [paths relative to their root]} under every root, built once."""
        if getattr(self, "_names", None) is None:
            self._names = paths.file_index([(os.path.realpath(r), []) for r in self.roots])
        return self._names

    def _length(self, rel):
        """The number of lines of `rel` under the app root or a contract root, or `None` when no root holds it."""
        for root in self.roots:
            base = os.path.realpath(root)
            path = os.path.realpath(os.path.join(base, rel))
            try:
                inside = os.path.commonpath([base, path]) == base
            except ValueError:
                inside = False
            if inside and os.path.isfile(path):
                if path not in self._lengths:
                    try:
                        with open(path, "rb") as fh:
                            data = fh.read()
                    except OSError:
                        continue
                    self._lengths[path] = data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)
                return self._lengths[path]
        return None

    def _resolve(self, text, number, path, first=None, last=None):
        """The failure of one citation, or `None`. Without a line range only the file must exist. A bare file name
        (`MainPayslipFeature.swift:287`) stands for the one file of that name under the roots, as in the catalog
        range check; no such file, or several, is a failure."""
        if "/" not in path:
            matches = self._by_name().get(path) or []
            path = matches[0] if len(matches) == 1 else path
        length = self._length(path)
        if length is None:
            return f"{text} (line {number}): file not found"
        if first is None:
            return None
        if first < 1 or last < first:
            return f"{text} (line {number}): not a line range"
        if last > length:
            return f"{text} (line {number}): the file has {length} lines"
        return None

    def _bare(self, value):
        """`(text, path, first, last)` of a bare catalog location: `path:line`, `path:line-line` or a path alone."""
        value = value.strip()
        m = _CITE.match(value)
        if m:
            return value, m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        return value, value, None, None

    def _catalog_cites(self):
        """`(number, text, path, first, last)` of every citation the renderer writes from a catalog without backticks:
        the Design column of section 2 (`carry-as-is (<app> <location>)`), a screen's `- **Source:**` line in section
        3 and the Source column of Appendix A. The renderer keeps their text format; the grader still resolves them."""
        app = re.escape(str(self.ctx.app))
        design = re.compile(r"^carry-as-is \(" + app + r" (.+?)(, line not resolved)?\)$")
        for number, text in self.spec.lines([HEADINGS[1]]):
            cells = [c.strip() for c in _ROW_SPLIT.split(text.strip().strip("|"))] if text.startswith("|") else []
            m = design.match(cells[2]) if len(cells) > 2 else None
            if m:
                yield (number, *self._bare(m.group(1)))
        for number, text in self.spec.lines([HEADINGS[2]]):
            m = re.match(r"^- \*\*Source:\*\* (.+)$", text)
            if m and not m.group(1).startswith(("UNKNOWN", "`")):
                yield (number, *self._bare(m.group(1)))
        rows = [(n, t) for n, t in self.spec.lines([APPENDICES[0]]) if t.startswith("|")]
        for number, text in rows:
            cells = [c.strip() for c in _ROW_SPLIT.split(text.strip().strip("|"))]
            if len(cells) == 7 and cells[6] and cells[6] != "Source" and not set(cells[6]) <= {"-"}:
                yield (number, *self._bare(cells[6]))

    def citations_resolve(self):
        items = []
        for number, line, code, section in self.spec.rows:
            if code or section == APPENDIX_F:
                continue
            for text, path, first, last in _cites(line):
                items.append(self._resolve(text, number, path, first, last))
        for number, text, path, first, last in self._catalog_cites():
            items.append(self._resolve(text, number, path, first, last))
        return [i for i in items if i]

    # ------------------------------------------------------------ unknowns

    def _rule_placeholders(self):
        """The numbers of the lines the renderer's own no-rule hint wrote in section 5, for use cases that exist."""
        shown = {self.ctx.shown[c["id"]] for c in self.ctx.cases}
        found = set()
        for number, text in self.spec.lines([HEADINGS[4]]):
            m = _NO_RULE_LINE.match(text)
            if text == _NO_RULES_LINE or (m and set(m.group(1).split(", ")) <= shown):
                found.add(number)
        return found

    def _listed_questions(self):
        """The `OQ-NNN` ids that section 8 lists as `- **OQ-NNN:** ...`."""
        return {m.group(1) for _, t in self.spec.lines([HEADINGS[7]]) for m in [_OQ_ITEM.match(t)] if m}

    def unknowns_have_owner(self):
        items, exempt, listed = [], self._rule_placeholders(), self._listed_questions()
        for number, text in self.spec.lines(BODY):
            if "UNKNOWN" not in text or _PLACEHOLDER in text or number in exempt:
                continue
            refs = _OQ_REF.findall(text)
            if refs and set(refs) <= listed:
                continue  # a structural UNKNOWN that points at an open question with its search note and owner
            low = text.lower()
            if not (re.search(r"\bsearched\b", low) and re.search(r"\bowner\b", low)):
                items.append(f"line {number}: {text.strip()[:70]}")
        return items

    def prose_complete(self):
        exempt = self._rule_placeholders()
        return [f"line {n}: {t.strip()[:70]}" for n, t in self.spec.lines(NOT_COVERAGE)
                if _PLACEHOLDER in t and n not in exempt]

    # ------------------------------------------------------------ banned nouns

    def banned_nouns(self):
        nouns = [n for n in ((self.cfg.get("options") or {}).get("bannedNouns") or []) if isinstance(n, str) and n]
        items = []
        for number, text in self.spec.lines(BODY):
            if text.startswith(OUT_OF_SCOPE_LEAD):
                continue  # the names of neighbour use cases and rules, quoted from the agents
            plain = _unmarked(text)
            for noun in nouns:
                if re.search(r"(?<!\w)" + re.escape(noun) + r"(?!\w)", plain):
                    items.append(f"{noun} (line {number})")
        return items

    # ------------------------------------------------------------ overrides

    def _known(self):
        """The ids each kind of override can name, from the catalogs, the inventory and the module."""
        c = self.ctx
        inv = out.load(self.dest, "inventory.json", {}) or {}
        module = out.load(self.dest, "module.json", {}) or {}
        flows = out.load(self.dest, "flows.json", {}) or {}
        screens = out.load(self.dest, "screens.json", {}) or {}
        cases = c.all_cases

        def gather(key):
            return {str(v) for case in cases for v in case.get(key) or [] if isinstance(v, str)}

        strings = inv.get("strings") if isinstance(inv.get("strings"), dict) else {}
        plat = inv.get("platform") if isinstance(inv.get("platform"), dict) else {}
        fields, text_keys = set(), set()
        for s in screens.get("screens") or []:
            if isinstance(s, dict) and s.get("id"):
                for keys, _, e in _element_rows(s["id"], [e for e in s.get("elements") or [] if isinstance(e, dict)]):
                    fields |= keys
                    if e.get("textKey"):
                        text_keys.add(str(e["textKey"]))

        def named(entry, *keys):
            if isinstance(entry, dict):
                for k in keys:
                    if entry.get(k):
                        return str(entry[k])
                return None
            return str(entry) if entry else None

        platform = set()
        for section, value in plat.items():
            if section == "permissions":
                continue
            platform.add(section)
            platform |= {f"{section}:{p}" for p in _platform_values(value)}
        counted = _Ledger(self.dest)
        counted.run()
        led = counted.items  # the ledger's own item keys, which `review --accept` records for an uncovered item
        known = {
            "useCase": {x["id"] for x in cases} | {x["alias"] for x in cases if x.get("alias")},
            "screen": {x["id"] for x in screens.get("screens") or [] if isinstance(x, dict) and x.get("id")},
            "endpoint": {e["id"] for e in out.load(self.dest, "endpoints.json", {}).get("endpoints") or []
                         if isinstance(e, dict) and e.get("id")},
            "flow": {x["id"] for x in flows.get("flows") or [] if isinstance(x, dict) and x.get("id")},
            "rule": {r["id"] for r in c.rules},
            "field": fields,
            "string": set(module.get("stringKeys") or []) | set(strings.get("keys") or {}) | gather("strings") | text_keys,
            "event": {named(e, "name") for e in inv.get("events") or []} | gather("events"),
            "storage": {named(s, "key", "name") for s in inv.get("storage") or []} | gather("storage"),
            "permission": {named(p, "key", "name") for p in plat.get("permissions") or []} | gather("permissions"),
            "platform": platform,
        }
        for kind, keys in led.items():
            if kind in known:
                known[kind] |= {str(k) for k in keys}
        return known

    def _old_names(self, ident):
        """The names the use case, screen, flow or rule `ident` had before a rename, from the workflow results."""
        prefix = str(ident).split("-")[0]
        registry = (out.load(self.dest, "ids.json", {}) or {}).get(prefix) or {}
        keys = {str(k).split("|")[0] for k, v in registry.items() if v == ident}
        raw = {}
        for name, lists in (("understand_result.json", ("useCases", "screens", "flows")), ("rules_result.json", ("rules",))):
            data = out.load(self.dest, name, {}) or {}
            for lst in lists:
                for entry in data.get(lst) or []:
                    if isinstance(entry, dict) and entry.get("name"):
                        raw.setdefault(norm(entry["name"]), set()).add(str(entry["name"]))
        return {n for k in keys for n in raw.get(k, ())}

    def overrides_reflected(self):
        ov = out.load(self.dest, "overrides.json", {}) or {}
        ov = ov if isinstance(ov, dict) else {}
        known, items = self._known(), []
        body = self.spec.text(NOT_COVERAGE)
        in_f = self.spec.text([APPENDIX_F])

        def is_known(kind, ident):
            pool = known.get(kind)
            if pool is None:
                return False
            if kind in ("permission", "platform"):
                return norm(ident) in {norm(p) for p in pool if p}
            return ident in pool

        for d in ov.get("drop") or []:
            if not isinstance(d, dict) or not d.get("id"):
                continue
            kind, ident = d.get("kind"), str(d["id"])
            if kind not in known:
                items.append(f"drop {ident}: unknown kind {kind}")
            elif not is_known(kind, ident):
                items.append(f"drop {kind} {ident}: unknown id, no catalog or inventory item has it")
            else:
                items += self._drop_items(kind, ident, body, in_f)
        for r in ov.get("rename") or []:
            if not isinstance(r, dict) or not r.get("id"):
                continue
            ident = str(r["id"])
            kind = {"UC": "useCase", "CAP": "useCase", "SCR": "screen", "FLOW": "flow", "RULE": "rule",
                    "EP": "endpoint"}.get(ident.split("-")[0])
            if not kind or not is_known(kind, ident):
                items.append(f"rename {ident}: unknown id")
            elif r.get("name") and not self.ctx.is_dropped(kind, ident):
                items += self._rename_items(ident, str(r["name"]), body)
        for key in ov.get("ids") or {}:
            if str(key) not in known["field"]:
                items.append(f"ids {key}: unknown field key")
        for m in ov.get("merge") or []:
            if isinstance(m, dict):
                registry = (out.load(self.dest, "ids.json", {}) or {}).get("UC") or {}
                retired = set(registry.values())
                if m.get("into") and str(m["into"]) not in known["useCase"]:
                    items.append(f"merge into {m['into']}: unknown id")
                items += [f"merge from {f}: unknown id" for f in m.get("from") or []
                          if str(f) not in known["useCase"] and str(f) not in retired]
        return items

    def _drop_items(self, kind, ident, body, in_f):
        if kind == "platform":
            return self._drop_platform(ident, in_f)
        text = self.spec.text(NOT_COVERAGE)
        idents = [ident]
        if kind == "useCase":
            alias = next((c.get("alias") for c in self.ctx.all_cases if c["id"] == ident), None)
            idents += [alias] if alias else []
        items = [f"drop {kind} {ident}: still in the spec" for i in idents if _token(i).search(text)]
        if not _token(ident).search(in_f):
            items.append(f"drop {kind} {ident}: missing from {APPENDIX_F[3:]}")
        return items

    def _drop_platform(self, ident, in_f):
        """A platform drop is `<section>:<value>` or a whole section; Appendix D shows `- **<section>:** a, b`."""
        section, _, value = ident.partition(":")
        items = []
        for line in self.spec.lines([APPENDICES[3]]):
            m = re.match(r"^- \*\*([^*]+):\*\* (.*)$", line[1])
            if m and m.group(1) == section and (not value or value in [v.strip() for v in m.group(2).split(",")]):
                items.append(f"drop platform {ident}: still in the spec")
                break
        if not _token(ident).search(in_f):
            items.append(f"drop platform {ident}: missing from {APPENDIX_F[3:]}")
        return items

    def _rename_items(self, ident, name, body):
        items = []
        if name not in body:
            items.append(f"rename {ident}: '{name}' is not in the spec")
        stale = [o for o in self._old_names(ident) if o != name and o in body.replace(name, "")]
        items += [f"rename {ident}: old name '{o}' is still in the spec" for o in sorted(stale)]
        return items

    # ------------------------------------------------------------ run

    def run(self):
        checks = []
        for name in CHECKS:
            items = getattr(self, name.replace("-", "_"))()
            checks.append({"name": name, "pass": not items, "detail": _detail(items)})
        return {"version": 1, "checks": checks, "pass": all(c["pass"] for c in checks)}


def run(dest, name="SPEC.md"):
    """Grade the spec `name` in the output folder `dest`, write grade.json and return it."""
    result = _Grader(dest, name).run()
    out.save(dest, "grade.json", result)
    return result


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    name = "SPEC.md"
    if "--name" in args:
        i = args.index("--name")
        if i + 1 >= len(args):
            print("usage: grade.py <out> [--name FILE]", file=sys.stderr)
            return 2
        name = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: grade.py <out> [--name FILE]", file=sys.stderr)
        return 2
    result = run(args[0], name)
    print(f"Grade: {'pass' if result['pass'] else 'fail'}")
    for c in result["checks"]:
        if not c["pass"]:
            print(f"  FAIL {c['name']}: {c['detail']}")
    print(f"Wrote {args[0]}: grade.json")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
