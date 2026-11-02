"""Compile SPEC.md from the catalogs and prose.json: one function per section, each returning a list of lines.

The renderer writes every table, id and citation it can take from the catalogs. A prose slot that `prose.json` does not
fill is written as `UNKNOWN — <what is missing>`, so the structure is complete before the spec writer has run. Output is
a pure function of the files in the output folder: no clock, no random order."""

import json
import os
import re

from . import out, paths
from .common import die
from .ids import element_slug
from .template import APPENDICES, CITE_RE, EVIDENCE_LABELS, HEADINGS, header

_LINE = re.compile(r":\d")
_VALID_ID = re.compile(r"^(?:UC|CAP)-\d{3,}$")
_RANK = {"P0": 0, "P1": 1, "P2": 2}


# ---------------------------------------------------------------- small helpers


def _text(value):
    """`value` on one line."""
    return " ".join(str(value if value is not None else "").split())


_CITE_TOKEN = re.compile(r"(?<![\w@+.\-/`])(" + CITE_RE + r")(?![\w`])")
NO_RULE = "No client-side rule; the server decides."
# the renderer's list of neighbour use cases and rules: names quoted from the agents, not requirements
OUT_OF_SCOPE_LEAD = "- **Out of scope, belongs to neighbour modules**"
# The two cited sentences that excuse a use case without a rule: the server decides, or a stated reason such as
# "No client-side rule: this use case only opens the assistant sheet." The reason must be a real clause.
NO_RULE_REASON = "No client-side rule: <reason>."
NO_RULE_RE = re.compile(r"\bNo client-side rule(?:; the server decides\.|: [^.`<>]{12,}\.)")


def _cited(value):
    """`value` on one line with every `path:line` or `path:line-line` in backticks, so each citation can be checked."""
    parts = re.split(r"(`[^`]*`)", _text(value))
    return "".join(p if p.startswith("`") else _CITE_TOKEN.sub(r"`\1`", p) for p in parts)


def _cell(value):
    return _text(value).replace("|", "\\|")


def _unknown(what):
    return f"UNKNOWN — {what}"


def _number(entry):
    return int(str(entry["id"]).rsplit("-", 1)[1])


def _table(head, rows):
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return lines


def _items(value):
    return [v for v in value if v] if isinstance(value, list) else []


def _cite(file, line=None):
    return f"{file}:{line}" if file and line else str(file or "")


class Context:
    """Everything the sections read, loaded once."""

    def __init__(self, dest):
        self.dest = dest
        self.cfg = out.load_config(dest)
        self.app = self.cfg["app"]["name"]
        self.locale = (self.cfg.get("options") or {}).get("locale", "en")
        self.overrides = out.load(dest, "overrides.json", {}) or {}
        self.drops = [d for d in self.overrides.get("drop") or [] if isinstance(d, dict) and d.get("id")]
        self.dropped = {(d.get("kind"), str(d["id"])): d.get("reason") for d in self.drops}
        self.inventory = out.load(dest, "inventory.json", {}) or {}
        self.module = out.load(dest, "module.json", {}) or {}
        self.ledger = out.load(dest, "ledger.json")
        prose = out.load(dest, "prose.json")
        # the writer may cite absolute or root-name paths: the spec shows them relative to their root
        self.prose = paths.relativize(prose, paths.roots(self.cfg)) if isinstance(prose, dict) else {}
        self.has_prose = bool(self.prose)
        all_cases = self._catalog("use-cases.json", "useCases")
        self.all_cases = all_cases
        self.cases = [c for c in all_cases if not self.is_dropped("useCase", c["id"])]
        self.screens = [s for s in self._catalog("screens.json", "screens") if not self.is_dropped("screen", s["id"])]
        self.flows = self._kept_flows(self._catalog("flows.json", "flows"))
        self.rules = self._catalog("rules.json", "rules")
        self.endpoints = [e for e in self._catalog("endpoints.json", "endpoints") if not self.is_dropped("endpoint", e["id"])]
        self.shown = {c["id"]: c.get("alias") or c["id"] for c in self.cases}  # the id the spec shows for a kept use case
        self.by_alias = {c["alias"]: c["id"] for c in all_cases if c.get("alias")}
        self.screen_names = {s["id"]: s["name"] for s in self.screens}

    def _catalog(self, name, key):
        data = out.load(self.dest, name)
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            die(f"{self.dest} has no usable {name} (run render.py catalogs first)")
        return sorted((e for e in data[key] if isinstance(e, dict) and e.get("id")), key=_number)

    def is_dropped(self, kind, ident):
        return (kind, str(ident)) in self.dropped

    def _kept_flows(self, flows):
        """The flows without dropped use cases: a step whose use cases are all dropped goes, and so does a flow left
        with no step; the dropped ids leave the steps that stay."""
        kept = []
        for flow in flows:
            steps = []
            for step in flow.get("steps") or []:
                ids = [u for u in step.get("useCases") or [] if not self.is_dropped("useCase", u)]
                if step.get("useCases") and not ids:
                    continue
                steps.append({**step, "useCases": ids})
            if steps or not flow.get("steps"):
                kept.append({**flow, "steps": steps})
        return kept

    def show(self, uc_ids):
        return ", ".join(self.shown.get(u, u) for u in uc_ids if not self.is_dropped("useCase", u)) or "none"

    def uc_of(self, ident):
        """The `UC-NNN` id of a use-case id or alias as written in the prose."""
        return self.by_alias.get(ident, ident)


# ---------------------------------------------------------------- header


def head(c):
    lines = header(c.cfg).splitlines()
    core = _items(c.module.get("core"))
    folders = sorted({os.path.dirname(f) or "." for f in core})
    lines += ["", "Module scope:",
              f"- Core: {len(core)} files in {', '.join(f'`{f}`' for f in folders) or 'UNKNOWN — no core files recorded'}."]
    for tp in c.module.get("touchPoints") or []:
        if isinstance(tp, dict) and tp.get("file"):
            lines.append(f"- Touch point: `{tp['file']}` ({_text(tp.get('reason')) or 'no reason recorded'}).")
    lines += ["", "Evidence labels: " + ", ".join(f"`{e}`" for e in EVIDENCE_LABELS)
              + ". `PROPOSED` marks anything the writer suggests."]
    return lines


# ---------------------------------------------------------------- the eight sections


def summary(c):
    text = _cited(c.prose.get("summary"))
    return [text or _unknown("summary not written yet")]


def _design(c, case):
    """`carry-as-is (<app> <file:line>)`: the first cited line of the use case, else its first screen's declaration."""
    files = [str(f) for f in _items(case.get("files"))]
    by_id = {s["id"]: s for s in c.screens}
    cite = next((f for f in files if _LINE.search(f)), None)
    if cite is None:
        cite = next((str(by_id[s]["file"]) for s in case.get("screens") or []
                     if s in by_id and _LINE.search(str(by_id[s].get("file") or ""))), None)
    if cite:
        return f"carry-as-is ({c.app} {cite})"
    if files:
        return f"carry-as-is ({c.app} {files[0]}, line not resolved)"
    return f"carry-as-is ({c.app}, {_oq(c, case['id'])})"


def _evidence(c, ref, label):
    """An evidence label as the spec shows it: a known label as it is, else the open question that asks for it."""
    return label if label in ("VERIFIED", "INFERRED", "PROPOSED") else _oq(c, ref)


def capabilities(c):
    rows = []
    for case in c.cases:
        screens = ", ".join(c.screen_names[s] for s in case.get("screens") or [] if s in c.screen_names) or "none"
        notes = " ".join(p for p in (f"{_evidence(c, case['id'], case.get('evidence'))}.", _text(case.get("description")),
                                     f"Personas: {', '.join(_items(case.get('personas')))}." if _items(case.get("personas")) else "") if p)
        rows.append([c.shown[case["id"]], case["name"], _design(c, case), screens, notes])
    return _table(["CAP", "Name", "Design", "Screens", "Notes"], rows) if rows else ["No use cases in the catalog."]


def _states(c, screen):
    written = ((c.prose.get("screens") or {}).get(screen["id"]) or {}).get("states")
    lines = []
    if isinstance(written, list) and written:
        for st in written:
            if isinstance(st, dict) and st.get("name"):
                ev = _cited(st.get("evidence"))
                lines.append(f"  - **{_text(st['name'])}:** {_cited(st.get('shows')) or _unknown('nothing recorded')}. "
                             f"Source: {ev or _unknown('no citation')}")
    else:
        for st in screen.get("states") or []:
            if isinstance(st, dict) and st.get("name"):
                lines.append(f"  - **{_text(st['name'])}:** {_text(st.get('shows')) or _oq(c, screen['id'])}. "
                             f"{_evidence(c, screen['id'], st.get('evidence'))}.")
    return lines or ["  - " + _unknown("no states found for this screen")]


def _catalog_states(c, screen):
    """The catalog's states when the writer gave none for the screen: they are what the spec shows."""
    written = ((c.prose.get("screens") or {}).get(screen["id"]) or {}).get("states")
    if isinstance(written, list) and written:
        return []
    return [st for st in screen.get("states") or [] if isinstance(st, dict) and st.get("name")]


def _screen_gaps(c, s):
    gaps = []
    unsure = [_text(st["name"]) for st in _catalog_states(c, s)
              if st.get("evidence") not in ("VERIFIED", "INFERRED", "PROPOSED") or not _text(st.get("shows"))]
    if unsure:
        gaps.append(f"what the user sees in the {', '.join(unsure)} state{'s' if len(unsure) > 1 else ''}")
    if not _items(s.get("actions")):
        gaps.append("the actions a user has")
    if not s.get("file"):
        gaps.append("where the screen is declared")
    return gaps


def screens(c):
    lines = []
    for s in c.screens:
        purpose = _cited(((c.prose.get("screens") or {}).get(s["id"]) or {}).get("purpose"))
        actions = [_text(a) for a in _items(s.get("actions"))]
        lines += [f"### {s['name']} ({s['id']}) — {c.show(s.get('useCases') or [])}", "",
                  f"- **Purpose/content:** {purpose or _unknown('purpose not written yet')}",
                  f"- **Actions:** {'; '.join(actions) or _oq(c, s['id'])}",
                  "- **States:**", *_states(c, s),
                  f"- **Source:** {s.get('file') or _oq(c, s['id'])}", ""]
    return lines or ["No screens in the catalog."]


def _field_rows(fields, missing="not recorded"):
    return [[f.get("name"), f.get("type") or missing,
             {True: "yes", False: "no"}.get(f.get("required"), missing), f.get("nullable") or missing,
             _field_source(f)]
            for f in fields if isinstance(f, dict)]


def _field_source(f):
    """The field's source as a backticked citation, so the grader checks its range; `-` when it has none."""
    src = f.get("source")
    if not src and isinstance(f.get("citations"), list) and f["citations"]:
        src = f["citations"][0]
    return f"`{_text(src)}`" if src else "-"


def _incomplete_fields(e):
    return [_text(f.get("name")) or "unnamed" for key in ("request", "response")
            for f in ((e.get(key) or {}).get("fields") or [])
            if isinstance(f, dict) and not (f.get("type") and f.get("required") in (True, False) and f.get("nullable"))]


def _clients(e):
    return [x for x in (e.get("clients") or ([e["client"]] if e.get("client") else [])) if isinstance(x, dict)]


def _endpoint_gaps(e):
    """What the catalog does not know about endpoint `e`, as the parts of one open question."""
    gaps = []
    if (e.get("label") or "UNKNOWN") == "UNKNOWN":
        gaps.append(f"the contract ({_text(e.get('reason')) or 'label UNKNOWN'})")
    if not _text(e.get("auth")):
        gaps.append("the auth it sends")
    if not _field_rows(((e.get("response") or {}).get("fields")) or []):
        gaps.append("the response fields")
    incomplete = _incomplete_fields(e)
    if incomplete:
        gaps.append(f"the type, required flag or nullability of {', '.join(incomplete)}")
    errors = [x for x in e.get("errors") or [] if isinstance(x, dict)]
    if not errors:
        gaps.append("the errors it handles and what the user sees")
    silent = [str(x.get("status")) for x in errors if not _text(x.get("reaction"))]
    if silent:
        gaps.append(f"what the user sees on {', '.join(silent)}")
    if not _clients(e):
        gaps.append("the client that builds it")
    if not isinstance(e.get("backend"), dict):
        gaps.append("the backend route")
    return gaps


def _case_gaps(case):
    gaps = []
    if case.get("evidence") not in ("VERIFIED", "INFERRED", "PROPOSED"):
        gaps.append(f"the code that implements it (evidence {_text(case.get('evidence')) or 'not recorded'})")
    if not _items(case.get("files")) and not case.get("screens"):
        gaps.append("the files that implement it")
    return gaps


def _rule_gaps(r):
    return [what for key, what in (("priority", "priority"), ("category", "category"),
                                   ("plainEnglish", "plain-English statement"), ("source", "source lines"))
            if not _text(r.get(key))]


def _files(values):
    return ", ".join(f"`{v}`" for v in values if v)


def open_question_entries(c):
    """Every open question of section 8 and OPEN_QUESTIONS.md, in order: the writer's, then one `OQ-NNN` per use case,
    screen and endpoint the catalog leaves incomplete, then one per rule below High confidence or with a field missing.
    Each is a dict with `id`, `question`, `searched`, `owner` and, for the structural ones, `ref` (the catalog id the
    question belongs to). Every UNKNOWN the renderer writes from a catalog points at one of these."""
    if getattr(c, "_open", None) is not None:
        return c._open
    entries = []
    for q in _items(c.prose.get("openQuestions")):
        if isinstance(q, dict):
            entries.append({"id": _text(q.get("id")) or "Q", "question": _cited(q.get("question")),
                            "searched": _cited(q.get("searched")) or _unknown("not recorded"),
                            "owner": _cited(q.get("owner")) or _unknown("not recorded"), "ref": None})
    owner = f"owner of {c.app}"
    structural = []
    for case in c.cases:
        gaps = _case_gaps(case)
        if gaps:
            structural.append({"question": f'What are {", ".join(gaps)} of the use case "{_text(case["name"])}" '
                                           f"({c.shown[case['id']]})?",
                               "searched": _files(_items(case.get("files"))) or "the module's core files",
                               "owner": owner, "ref": case["id"]})
    for s in c.screens:
        gaps = _screen_gaps(c, s)
        if gaps:
            structural.append({"question": f"What are {', '.join(gaps)} of the screen {s['name']} ({s['id']})?",
                               "searched": _files([s.get("file")]) or "the module's screen files",
                               "owner": owner, "ref": s["id"]})
    for e in c.endpoints:
        gaps = _endpoint_gaps(e)
        if gaps:
            files = ", ".join(f"`{x.get('file')}`" for x in _clients(e) if x.get("file"))
            structural.append({"question": f"What are {', '.join(gaps)} of {e['method']} {endpoint_path(e)} ({e['id']})?",
                               "searched": files or "the module's network clients", "owner": owner, "ref": e["id"]})
    for r in c.rules:
        missing = _rule_gaps(r)
        if (r.get("confidence") != "High" or missing) and not (r.get("useCase") and c.is_dropped("useCase", r["useCase"])):
            if r.get("confidence") != "High":
                question = _text(r.get("question")) or (f'Is the rule "{_text(r.get("name"))}" right as stated? Its '
                                                         f"confidence is {r.get('confidence') or 'not recorded'}.")
            else:
                question = f'What completes the rule "{_text(r.get("name"))}"?'
            if missing:
                question += f" The rule card does not record its {_and(missing)}."
            structural.append({"question": f"{question} ({r['id']})", "searched": _rule_searched(c, r),
                               "owner": owner, "ref": r["id"]})
    for n, entry in enumerate(structural, 1):
        entry["id"] = f"OQ-{n:03d}"
    c._open = entries + structural
    return c._open


def _and(items):
    """`a`, `a and b`, `a, b and c`."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _rule_searched(c, r):
    """What was searched for the rule `r`: its source lines, else the rule card and the files of its use case."""
    if r.get("source"):
        return f"`{r.get('source')}`"
    case = next((u for u in c.all_cases if u["id"] == r.get("useCase")), None)
    files = _files(sorted({str(f) for f in _items(case.get("files"))})) if case else ""
    if case and files:
        return f"the rule card in `rules_result.json` and the files of {c.shown.get(case['id'], case['id'])} ({files})"
    return "the rule card in `rules_result.json`, which names no source lines and no use case with files"


def _oq(c, ref):
    """`UNKNOWN (open question OQ-NNN)` for the open question of endpoint or rule `ref`."""
    found = next((q["id"] for q in open_question_entries(c) if q.get("ref") == ref), None)
    return f"UNKNOWN (open question {found})" if found else _unknown("no open question recorded")


def endpoint_path(e):
    """The path of endpoint `e`, or `link <expression>` for a server link whose path no backend code named yet."""
    return e.get("path") or (f"link {e['followsLink']}" if e.get("followsLink") else "path unknown")


def endpoints(c):
    lines = []
    for e in c.endpoints:
        backend = e.get("backend")
        label = e.get("label") or "UNKNOWN"
        lines += [f"### {e['id']} — {e['method']} {endpoint_path(e)} ({_oq(c, e['id']) if label == 'UNKNOWN' else label})", "",
                  f"- **Capabilities:** {c.show(e.get('useCases') or [])}"]
        if e.get("followsLink"):
            lines.append(f"- **Follows link:** {_text(e['followsLink'])}, sent by the server"
                         + (f"; built at `{e['linkSource']}`" if e.get("linkSource") else ""))
        if e.get("paging"):
            lines.append(f"- **Paging:** {_text(e['paging'])}")
        lines.append(f"- **Auth:** {_text(e.get('auth')) or _oq(c, e['id'])}")
        if isinstance(backend, dict) and backend.get("auth"):
            lines[-1] += f"; backend: {_text(backend['auth'])}"
        for label, key in (("Request fields", "request"), ("Response fields", "response")):
            rows = _field_rows(((e.get(key) or {}).get("fields")) or [], _oq(c, e["id"]))
            if rows:
                lines += [f"- **{label}:**", ""] + _table(["Name", "Type", "Required", "Nullable", "Source"], rows) + [""]
            else:
                lines.append(f"- **{label}:** " + ("none recorded" if key == "request" else _oq(c, e["id"])))
        errors = [x for x in e.get("errors") or [] if isinstance(x, dict)]
        if errors:
            lines.append("- **Errors and UI reaction:**")
            lines += [f"  - {x.get('status')}: {_text(x.get('reaction')) or _oq(c, e['id'])}" for x in errors]
        else:
            lines.append("- **Errors and UI reaction:** " + _oq(c, e["id"]))
        clients = _clients(e)
        lines.append("- **Client:** " + ("; ".join(f"`{x.get('file')}` ({x.get('type') or 'type unknown'})" for x in clients)
                                         or _oq(c, e["id"])))
        if isinstance(backend, dict):
            lines.append(f"- **Backend:** {backend.get('repo') or 'repository unknown'} "
                         f"`{_cite(backend.get('file'), backend.get('line'))}`")
        else:
            lines.append("- **Backend:** " + _oq(c, e["id"]))
        for d in e.get("disagreements") or []:
            if isinstance(d, dict):
                lines.append(f"- **Disagreement on `{d.get('field')}`:** client `{d.get('client')}`, backend `{d.get('backend')}`. "
                             f"{_text(d.get('note'))}")
        lines.append("")
    return lines or ["No endpoints in the catalog."]


def _param(p):
    if isinstance(p, dict):
        return f"{_text(p.get('name'))} = {_text(p.get('value'))}"
    return _text(p)


def _rule(c, r):
    uc = r.get("useCase")
    gap = _oq(c, r["id"])
    lines = [f"### {r['id']} — {_text(r.get('name'))}", "",
             f"- **Priority:** {r.get('priority') or gap}; **category:** {r.get('category') or gap}; "
             f"**confidence:** {r.get('confidence') or gap}; **use case:** {c.shown.get(uc, uc) if uc else 'none'}",
             f"- **Rule:** {_text(r.get('plainEnglish')) or gap}",
             f"- **Given:** {_text(r.get('given'))}",
             f"- **When:** {_text(r.get('when'))}",
             f"- **Then:** {_text(r.get('then'))}"]
    params = [_param(p) for p in _items(r.get("parameters"))]
    if params:
        lines.append("- **Parameters:** " + "; ".join(params))
    edges = [_text(x) for x in _items(r.get("edgeCases"))]
    if edges:
        lines.append("- **Edge cases:** " + "; ".join(edges))
    if r.get("suspectedDefect"):
        lines.append(f"- **Suspected defect in the old app (do not copy):** {_text(r['suspectedDefect'])}")
    lines.append(f"- **Source:** `{r.get('source')}`" if r.get("source") else "- **Source:** " + gap)
    if r.get("confidence") != "High":
        oq = next((q["id"] for q in open_question_entries(c) if q.get("ref") == r["id"]), None)
        if r.get("question") and oq:
            lines.append(f"- **Question:** {_text(r['question'])} (open question {oq})")
        else:
            lines.append(f"- **Question:** {_oq(c, r['id'])}")
    return lines + [""]


def rules(c):
    shown = [r for r in c.rules if not (r.get("useCase") and c.is_dropped("useCase", r["useCase"]))]
    ordered = sorted(shown, key=lambda r: (_RANK.get(r.get("priority"), 3), _number(r)))
    lines = []
    for r in ordered:
        lines += _rule(c, r)
    if not lines:
        lines = [_unknown("no rules extracted"), ""]
    perms = [[c.shown[u["id"]], ", ".join(_items(u.get("personas"))) or "none", "; ".join(p for p in _items(u.get("permissions")) if not c.is_dropped("permission", p)) or "none"]
             for u in c.cases]
    lines += ["### Permissions", ""] + _table(["CAP", "Personas", "Permissions and gates"], perms) + [""]
    ruled = {r.get("useCase") for r in shown}
    bare = [c.shown[u["id"]] for u in c.cases if u["id"] not in ruled and not _says_no_rule(c, u)]
    if bare:
        lines += ["### Use cases without a rule", "",
                  _unknown("no rule extracted for " + ", ".join(bare)
                           + f'; add a rule or write "{NO_RULE}" or "{NO_RULE_REASON}" with a citation'), ""]
    return lines


_SPAN = re.compile(r"`([^`\n]+)`")
_CITE_ONLY = re.compile(r"^" + CITE_RE + r"$")


def _has_citation(line):
    """True when `line` holds a backticked `path:line` or `path:line-line`, as the grader reads one."""
    return any(_CITE_ONLY.match(part) and re.match(r"^\S+?:\d+(?:-\d+)?$", part) for span in _SPAN.finditer(line)
               for part in re.split(r"\s*[,;]\s*", span.group(1).strip()))


def _says_no_rule(c, case):
    """True when the spec states a cited no-rule sentence (NO_RULE_RE) for `case`: in an acceptance criterion that names it, or in
    the block of one of its screens. The same test as the grader's rules-per-use-case, so both list the same use cases."""
    shown = {case["id"], c.shown[case["id"]]}
    lines = [t for t in criteria(c) if (m := re.match(r"^- \*\*AC\d+ \(([^)]*)\):\*\*", t))
             and {i.strip() for i in m.group(1).split(",")} & shown]
    ids = set(case.get("screens") or []) | {s["id"] for s in c.screens if case["id"] in (s.get("useCases") or [])}
    inside = False
    for t in screens(c):
        if t.startswith("### "):
            inside = any(f"({s})" in t for s in ids)
        if inside:
            lines.append(t)
    return any(NO_RULE_RE.search(t) and _has_citation(t) for t in lines)


def criteria(c):
    """The numbered acceptance criteria: the written ones in order, then a placeholder for every use case with none."""
    entries, covered, orphans = [], set(), []
    for raw in _items(c.prose.get("criteria")):
        if not isinstance(raw, dict):
            continue
        ids, gone = [], False
        for ident in _items(raw.get("ids")):
            ident = str(ident)
            uc = c.uc_of(ident)
            if c.is_dropped("useCase", uc):
                gone = True
                continue
            shown = c.shown.get(uc, ident)
            if _VALID_ID.match(shown) and shown not in ids:
                ids.append(shown)
                covered.add(uc)
        text, ev = _cited(raw.get("text")), _cited(raw.get("evidence"))
        if not ids:
            if not gone:
                orphans.append(f"- {_unknown('criterion without a use case id')}: {text}")
            continue
        entries.append((ids, f"{text or _unknown('criterion text missing')} Source: {ev or _unknown('no citation')}"))
    for case in c.cases:
        if case["id"] not in covered:
            entries.append(([c.shown[case["id"]]], _unknown("criterion not written yet")))
    lines = [f"- **AC{n} ({', '.join(ids)}):** {text}" for n, (ids, text) in enumerate(entries, 1)]
    return (lines or [_unknown("no use cases to cover")]) + orphans


def out_of_scope_line(c):
    """One line naming the neighbour use cases and rules found only in touch files, or None."""
    data = out.load(c.dest, "out-of-scope.json", {}) or {}
    parts = []
    for key, label in (("useCases", "use cases"), ("rules", "rules")):
        items = [e for e in data.get(key) or [] if isinstance(e, dict) and e.get("id")] if isinstance(data, dict) else []
        if items:
            parts.append(f"{label} " + "; ".join(f"{e['id']} {e.get('name') or ''}".strip() for e in items))
    if not parts:
        return None
    return (OUT_OF_SCOPE_LEAD + " (found only in touch files; see out-of-scope.json): "
            + ". ".join(parts) + ".")


def dependencies(c):
    deps = [f"- {_cited(d)}" for d in _items(c.prose.get("dependencies"))]
    extra = out_of_scope_line(c)
    if not deps:
        deps = [_unknown("dependencies and decisions not written yet")]
    return deps + ([extra] if extra else [])


def open_questions(c):
    lines = [f"- **{q['id']}:** {q['question']} Searched: {q['searched']}. Owner: {q['owner']}."
             for q in open_question_entries(c)]
    if lines:
        return lines
    return ["None recorded."] if c.has_prose else [_unknown("open questions not written yet")]


# ---------------------------------------------------------------- appendices


def _element_rows(sid, elements):
    """`(key, element)` per element, with the key an override uses and the key after de-duplication."""
    used, rows = set(), []
    for i, e in enumerate(elements):
        base = element_slug(e, i)
        name = f"{base}-{i}" if base in used else base
        used.add(name)
        rows.append(({f"{sid}.{base}", f"{sid}.{name}"}, f"{sid}.{name}", e))
    return rows


def fields_and_ids(c):
    lines = []
    for s in c.screens:
        rows = [[key.split(".", 1)[1], e.get("kind"), "" if c.is_dropped("string", e.get("textKey")) else e.get("textKey") or "", e.get("text") or "", e.get("identifier") or "",
                 e.get("proposedId"), _cite(e.get("file"), e.get("line"))]
                for keys, key, e in _element_rows(s["id"], s.get("elements") or [])
                if not any(c.is_dropped("field", k) for k in keys)]
        lines += [f"### {s['id']} {s['name']}", ""]
        lines += (_table(["Element", "Kind", "Text key", "Text", "Existing id", "Proposed id", "Source"], rows)
                  if rows else ["No elements recorded."]) + [""]
    return lines or ["UNKNOWN — no screens in the catalog"]


def data(c):
    rows = [[d.get("entity"), d.get("fields"), d.get("storage"), d.get("lifetime"), _cited(d.get("evidence")) or _unknown("no citation")]
            for d in _items(c.prose.get("data")) if isinstance(d, dict)]
    return (_table(["Entity", "Fields", "Storage", "Lifetime", "Evidence"], rows) if rows
            else [_unknown("data entities not written yet")])


def keep_and_drop(c):
    written = c.prose.get("keepDrop") if isinstance(c.prose.get("keepDrop"), dict) else {}
    lines = []
    for case in c.cases:
        entry = written.get(case["id"]) or written.get(c.shown[case["id"]]) or {}
        keep = [_cited(k) for k in _items(entry.get("keep"))]
        drop = [d for d in _items(entry.get("drop")) if isinstance(d, dict)]
        lines += [f"### {c.shown[case['id']]} {case['name']}", "", "- **Keep:**"]
        lines += [f"  - {k}" for k in keep] or ["  - " + _unknown("behaviour to keep not written yet")]
        lines.append("- **Drop:**")
        lines += [f"  - {_cited(d.get('what'))} (`{d.get('file')}`)" for d in drop] or [
            "  - " + _unknown("implementation to drop not written yet")]
        lines.append("")
    return lines or ["UNKNOWN — no use cases in the catalog"]


def _name(item, key):
    return str(item.get(key)) if isinstance(item, dict) else str(item)


def _platform_value(value):
    if isinstance(value, bool):
        return "yes"
    if isinstance(value, list):
        return ", ".join(v if isinstance(v, str) else json.dumps(v, sort_keys=True, ensure_ascii=False) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _kept_platform(c, plat):
    """The platform section without dropped items: a permission by its key (kind `permission`), any other list member
    as `<section>:<value>` and a whole section by its name (kind `platform`)."""
    kept = {}
    for section, value in plat.items():
        if section != "permissions" and c.is_dropped("platform", section):
            continue
        if isinstance(value, list):
            def name(v):
                return str(v.get("key") or v.get("name") or v.get("id")) if isinstance(v, dict) else str(v)
            if section == "permissions":
                value = [v for v in value if not c.is_dropped("permission", name(v))]
            else:
                value = [v for v in value if not c.is_dropped("platform", f"{section}:{name(v)}")]
        kept[section] = value
    return kept


def strings_and_platform(c):
    inv = c.inventory
    strings = inv.get("strings") if isinstance(inv.get("strings"), dict) else {}
    values = strings.get("values") if isinstance(strings.get("values"), dict) else {}
    keys = _items(c.module.get("stringKeys")) or sorted((strings.get("keys") or {}))
    keys = sorted(k for k in keys if not c.is_dropped("string", k))
    lines = [f"### Strings ({c.locale})", ""]
    lines += (_table(["Key", "Text"], [[k, values.get(k) or ""] for k in keys]) if keys else ["None found."])
    events = sorted((e for e in _items(inv.get("events")) if not c.is_dropped("event", _name(e, "name"))),
                    key=lambda e: _name(e, "name"))
    lines += ["", "### Analytics events", ""]
    lines += (_table(["Event", "Source"], [[_name(e, "name"), e.get("file") if isinstance(e, dict) else ""] for e in events])
              if events else ["None found."])
    storage = [s for s in _items(inv.get("storage"))
               if not (isinstance(s, dict) and c.is_dropped("storage", s.get("key") or s.get("name")))]
    lines += ["", "### Storage keys", ""]
    lines += (_table(["Kind", "Key", "Source"], [[s.get("kind"), s.get("key") or s.get("name"), s.get("file")]
                                                 for s in storage if isinstance(s, dict)]) if storage else ["None found."])
    plat = _kept_platform(c, inv.get("platform") if isinstance(inv.get("platform"), dict) else {})
    lines += ["", "### Platform", ""]
    lines += [f"- **{k}:** {_platform_value(plat[k])}" for k in sorted(plat) if plat[k]] or ["None found."]
    return lines


def flows(c):
    lines = []
    for f in c.flows:
        lines += [f"### {f['id']} — {_text(f.get('name'))}", "", f"Persona: {_text(f.get('persona')) or _unknown('not recorded')}", ""]
        for n, step in enumerate(f.get("steps") or [], 1):
            screen = step.get("screen")
            lines.append(f"{n}. {screen + ' ' + c.screen_names[screen] if screen in c.screen_names else 'no screen'}"
                         f" ({c.show(step.get('useCases') or [])}): {_text(step.get('action'))}")
        lines.append("")
    return lines or ["UNKNOWN — no flows in the catalog"]


def coverage(c):
    lines = []
    led = c.ledger if isinstance(c.ledger, dict) else None
    if led is None:
        lines.append("Coverage not computed yet: run ledger.py")
    else:
        classes = led.get("classes") if isinstance(led.get("classes"), dict) else {}
        thresholds = led.get("thresholds") if isinstance(led.get("thresholds"), dict) else {}
        lines += [f"Result: {'pass' if led.get('pass') else 'fail'}", ""]
        lines += _table(["Class", "Covered", "Total", "Threshold"],
                        [[k, v.get("covered"), v.get("total"), thresholds.get(k, "")] for k, v in sorted(classes.items())
                         if isinstance(v, dict)])
        for k, v in sorted(classes.items()):
            unc = [u for u in (v.get("uncovered") or []) if isinstance(u, dict)] if isinstance(v, dict) else []
            if unc:
                lines += ["", f"Uncovered {k}:"]
                lines += [f"- {_text(u.get('item'))}: {_text(u.get('reason')) or _unknown('no reason given')}" for u in unc]
    if c.drops:
        lines += ["", "Left out by `overrides.json`:", ""]
        lines += _table(["Kind", "Id", "Reason"], [[d.get("kind"), d["id"], d.get("reason") or _unknown("no reason given")]
                                                   for d in c.drops])
    return lines


# ---------------------------------------------------------------- the file

_SECTIONS = [summary, capabilities, screens, endpoints, rules, criteria, dependencies, open_questions]
_APPENDICES = [fields_and_ids, data, keep_and_drop, strings_and_platform, flows, coverage]


def render(dest):
    """The text of the spec for the output folder `dest`."""
    c = Context(dest)
    lines = head(c)
    for heading, section in list(zip(HEADINGS, _SECTIONS)) + list(zip(APPENDICES, _APPENDICES)):
        body = section(c)
        while body and not body[-1]:
            body = body[:-1]
        lines += ["", heading, ""] + body
    return "\n".join(lines) + "\n"


_OWNED = {"ledger.md", "review.md", "inventory.md", "open_questions.md"}  # lower case; every `.json` is owned too


def target(dest, name):
    """`name` checked to be a file inside `dest`. Exit 2 when it is absolute or leaves `dest`."""
    root = os.path.realpath(dest)
    try:
        inside = bool(name) and not os.path.isabs(name) and os.path.commonpath(
            [root, os.path.realpath(os.path.join(root, name))]) == root and os.path.realpath(os.path.join(root, name)) != root
    except ValueError:
        inside = False
    if not inside:
        die(f"--name {name!r} must be a file inside {dest}")
    rel = os.path.relpath(os.path.realpath(os.path.join(root, name)), root).replace(os.sep, "/").lower()
    if rel.endswith(".json") or rel in _OWNED or rel.split("/")[0] == "shards":
        die(f"--name {name!r} is a file the tools own in {dest}; choose another name")
    return name


def write(dest, name="SPEC.md"):
    """Render the spec and write it to `name` in `dest`. Return the text."""
    name = target(dest, name)
    text = render(dest)
    out.save_text(dest, name, text)
    return text
