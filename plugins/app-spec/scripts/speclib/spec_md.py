"""Compile SPEC.md from the catalogs and prose.json: one function per section, each returning a list of lines.

The renderer writes every table, id and citation it can take from the catalogs. A prose slot that `prose.json` does not
fill is written as `UNKNOWN — <what is missing>`, so the structure is complete before the spec writer has run. Output is
a pure function of the files in the output folder: no clock, no random order."""

import json
import os
import re

from . import out
from .common import die
from .ids import element_slug
from .template import APPENDICES, EVIDENCE_LABELS, HEADINGS, header

_LINE = re.compile(r":\d")
_VALID_ID = re.compile(r"^(?:UC|CAP)-\d{3,}$")
_RANK = {"P0": 0, "P1": 1, "P2": 2}


# ---------------------------------------------------------------- small helpers


def _text(value):
    """`value` on one line."""
    return " ".join(str(value if value is not None else "").split())


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
        self.prose = prose if isinstance(prose, dict) else {}
        self.has_prose = bool(self.prose)
        all_cases = self._catalog("use-cases.json", "useCases")
        self.all_cases = all_cases
        self.cases = [c for c in all_cases if not self.is_dropped("useCase", c["id"])]
        self.screens = [s for s in self._catalog("screens.json", "screens") if not self.is_dropped("screen", s["id"])]
        self.flows = self._catalog("flows.json", "flows")
        self.rules = self._catalog("rules.json", "rules")
        self.endpoints = [e for e in self._catalog("endpoints.json", "endpoints") if not self.is_dropped("endpoint", e["id"])]
        self.shown = {c["id"]: c.get("alias") or c["id"] for c in all_cases}  # the id the spec shows for a use case
        self.by_alias = {c["alias"]: c["id"] for c in all_cases if c.get("alias")}
        self.screen_names = {s["id"]: s["name"] for s in self.screens}

    def _catalog(self, name, key):
        data = out.load(self.dest, name)
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            die(f"{self.dest} has no usable {name} (run render.py catalogs first)")
        return sorted((e for e in data[key] if isinstance(e, dict) and e.get("id")), key=_number)

    def is_dropped(self, kind, ident):
        return (kind, str(ident)) in self.dropped

    def show(self, uc_ids):
        return ", ".join(self.shown.get(u, u) for u in uc_ids) or "none"

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
    text = _text(c.prose.get("summary"))
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
        return f"carry-as-is ({c.app} {files[0]}, line UNKNOWN)"
    return f"carry-as-is ({c.app} UNKNOWN: no file cited)"


def capabilities(c):
    rows = []
    for case in c.cases:
        screens = ", ".join(c.screen_names[s] for s in case.get("screens") or [] if s in c.screen_names) or "none"
        notes = " ".join(p for p in (f"{case.get('evidence') or 'UNKNOWN'}.", _text(case.get("description")),
                                     f"Personas: {', '.join(_items(case.get('personas')))}." if _items(case.get("personas")) else "") if p)
        rows.append([c.shown[case["id"]], case["name"], _design(c, case), screens, notes])
    return _table(["CAP", "Name", "Design", "Screens", "Notes"], rows) if rows else ["UNKNOWN — no use cases in the catalog"]


def _states(c, screen):
    written = ((c.prose.get("screens") or {}).get(screen["id"]) or {}).get("states")
    lines = []
    if isinstance(written, list) and written:
        for st in written:
            if isinstance(st, dict) and st.get("name"):
                ev = _text(st.get("evidence"))
                lines.append(f"  - **{_text(st['name'])}:** {_text(st.get('shows')) or _unknown('nothing recorded')}. "
                             f"Source: {ev or _unknown('no citation')}")
    else:
        for st in screen.get("states") or []:
            if isinstance(st, dict) and st.get("name"):
                lines.append(f"  - **{_text(st['name'])}:** {_text(st.get('shows')) or _unknown('nothing recorded')}. "
                             f"{st.get('evidence') or 'UNKNOWN'}.")
    return lines or ["  - " + _unknown("no states found for this screen")]


def screens(c):
    lines = []
    for s in c.screens:
        purpose = _text(((c.prose.get("screens") or {}).get(s["id"]) or {}).get("purpose"))
        actions = [_text(a) for a in _items(s.get("actions"))]
        lines += [f"### {s['name']} ({s['id']}) — {c.show(s.get('useCases') or [])}", "",
                  f"- **Purpose/content:** {purpose or _unknown('purpose not written yet')}",
                  f"- **Actions:** {'; '.join(actions) or _unknown('no actions found')}",
                  "- **States:**", *_states(c, s),
                  f"- **Source:** {s.get('file') or _unknown('no declaration cited')}", ""]
    return lines or ["UNKNOWN — no screens in the catalog"]


def _field_rows(fields):
    return [[f.get("name"), f.get("type") or "UNKNOWN",
             {True: "yes", False: "no"}.get(f.get("required"), "UNKNOWN"), f.get("nullable") or "UNKNOWN"]
            for f in fields if isinstance(f, dict)]


def endpoints(c):
    lines = []
    for e in c.endpoints:
        backend = e.get("backend")
        lines += [f"### {e['id']} — {e['method']} {e['path']} ({e.get('label') or 'UNKNOWN'})", "",
                  f"- **Capabilities:** {c.show(e.get('useCases') or [])}",
                  f"- **Auth:** {_text(e.get('auth')) or _unknown('no auth recorded')}"]
        if isinstance(backend, dict) and backend.get("auth"):
            lines[-1] += f"; backend: {_text(backend['auth'])}"
        for label, key in (("Request fields", "request"), ("Response fields", "response")):
            rows = _field_rows(((e.get(key) or {}).get("fields")) or [])
            if rows:
                lines += [f"- **{label}:**", ""] + _table(["Name", "Type", "Required", "Nullable"], rows) + [""]
            else:
                lines.append(f"- **{label}:** " + ("none recorded" if key == "request" else _unknown("no response fields recorded")))
        errors = [x for x in e.get("errors") or [] if isinstance(x, dict)]
        if errors:
            lines.append("- **Errors and UI reaction:**")
            lines += [f"  - {x.get('status')}: {_text(x.get('reaction')) or _unknown('no reaction recorded')}" for x in errors]
        else:
            lines.append("- **Errors and UI reaction:** " + _unknown("no error handling found"))
        clients = e.get("clients") or ([e["client"]] if e.get("client") else [])
        lines.append("- **Client:** " + ("; ".join(f"`{x.get('file')}` ({x.get('type') or 'type unknown'})" for x in clients)
                                         or _unknown("no client cited")))
        if isinstance(backend, dict):
            lines.append(f"- **Backend:** {backend.get('repo') or 'repository unknown'} "
                         f"`{_cite(backend.get('file'), backend.get('line'))}`")
        else:
            lines.append("- **Backend:** " + _unknown("no backend file given or found"))
        for d in e.get("disagreements") or []:
            if isinstance(d, dict):
                lines.append(f"- **Disagreement on `{d.get('field')}`:** client `{d.get('client')}`, backend `{d.get('backend')}`. "
                             f"{_text(d.get('note'))}")
        lines.append("")
    return lines or ["UNKNOWN — no endpoints in the catalog"]


def _param(p):
    if isinstance(p, dict):
        return f"{_text(p.get('name'))} = {_text(p.get('value'))}"
    return _text(p)


def _rule(c, r):
    uc = r.get("useCase")
    lines = [f"### {r['id']} — {_text(r.get('name'))}", "",
             f"- **Priority:** {r.get('priority') or 'UNKNOWN'}; **category:** {r.get('category') or 'UNKNOWN'}; "
             f"**confidence:** {r.get('confidence') or 'UNKNOWN'}; **use case:** {c.shown.get(uc, uc) if uc else 'none'}",
             f"- **Rule:** {_text(r.get('plainEnglish')) or _unknown('no plain-English statement')}",
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
    lines.append(f"- **Source:** `{r.get('source')}`" if r.get("source") else "- **Source:** " + _unknown("no source cited"))
    if r.get("confidence") != "High":
        lines.append(f"- **Question:** {_text(r.get('question')) or _unknown('no question recorded')}")
    return lines + [""]


def rules(c):
    shown = [r for r in c.rules if not (r.get("useCase") and c.is_dropped("useCase", r["useCase"]))]
    ordered = sorted(shown, key=lambda r: (_RANK.get(r.get("priority"), 3), _number(r)))
    lines = []
    for r in ordered:
        lines += _rule(c, r)
    if not lines:
        lines = [_unknown("no rules extracted"), ""]
    perms = [[c.shown[u["id"]], ", ".join(_items(u.get("personas"))) or "none", "; ".join(_items(u.get("permissions"))) or "none"]
             for u in c.cases]
    lines += ["### Permissions", ""] + _table(["CAP", "Personas", "Permissions and gates"], perms) + [""]
    ruled = {r.get("useCase") for r in shown}
    bare = [c.shown[u["id"]] for u in c.cases if u["id"] not in ruled]
    if bare:
        lines += ["### Use cases without a rule", "",
                  _unknown("no rule extracted for " + ", ".join(bare)
                           + '; add a rule or write "no client-side rule, server decides" with a citation'), ""]
    return lines


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
        text, ev = _text(raw.get("text")), _text(raw.get("evidence"))
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


def dependencies(c):
    deps = [_text(d) for d in _items(c.prose.get("dependencies"))]
    return [f"- {d}" for d in deps] or [_unknown("dependencies and decisions not written yet")]


def open_questions(c):
    lines = []
    for q in _items(c.prose.get("openQuestions")):
        if isinstance(q, dict):
            lines.append(f"- **{_text(q.get('id')) or 'Q'}:** {_text(q.get('question'))} "
                         f"Searched: {_text(q.get('searched')) or _unknown('not recorded')}. "
                         f"Owner: {_text(q.get('owner')) or _unknown('not recorded')}.")
    for r in c.rules:
        if r.get("confidence") != "High" and r.get("question") and not (
                r.get("useCase") and c.is_dropped("useCase", r["useCase"])):
            lines.append(f"- **{r['id']}:** {_text(r['question'])} Source: `{r.get('source')}`. Owner: "
                         + _unknown("not recorded"))
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
        rows = [[key.split(".", 1)[1], e.get("kind"), e.get("textKey") or "", e.get("text") or "", e.get("identifier") or "",
                 e.get("proposedId"), _cite(e.get("file"), e.get("line"))]
                for keys, key, e in _element_rows(s["id"], s.get("elements") or [])
                if not any(c.is_dropped("field", k) for k in keys)]
        lines += [f"### {s['id']} {s['name']}", ""]
        lines += (_table(["Element", "Kind", "Text key", "Text", "Existing id", "Proposed id", "Source"], rows)
                  if rows else ["No elements recorded."]) + [""]
    return lines or ["UNKNOWN — no screens in the catalog"]


def data(c):
    rows = [[d.get("entity"), d.get("fields"), d.get("storage"), d.get("lifetime"), d.get("evidence") or _unknown("no citation")]
            for d in _items(c.prose.get("data")) if isinstance(d, dict)]
    return (_table(["Entity", "Fields", "Storage", "Lifetime", "Evidence"], rows) if rows
            else [_unknown("data entities not written yet")])


def keep_and_drop(c):
    written = c.prose.get("keepDrop") if isinstance(c.prose.get("keepDrop"), dict) else {}
    lines = []
    for case in c.cases:
        entry = written.get(case["id"]) or written.get(c.shown[case["id"]]) or {}
        keep = [_text(k) for k in _items(entry.get("keep"))]
        drop = [d for d in _items(entry.get("drop")) if isinstance(d, dict)]
        lines += [f"### {c.shown[case['id']]} {case['name']}", "", "- **Keep:**"]
        lines += [f"  - {k}" for k in keep] or ["  - " + _unknown("behaviour to keep not written yet")]
        lines.append("- **Drop:**")
        lines += [f"  - {_text(d.get('what'))} (`{d.get('file')}`)" for d in drop] or [
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
    storage = _items(inv.get("storage"))
    lines += ["", "### Storage keys", ""]
    lines += (_table(["Kind", "Key", "Source"], [[s.get("kind"), s.get("key") or s.get("name"), s.get("file")]
                                                 for s in storage if isinstance(s, dict)]) if storage else ["None found."])
    plat = inv.get("platform") if isinstance(inv.get("platform"), dict) else {}
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
    return name


def write(dest, name="SPEC.md"):
    """Render the spec and write it to `name` in `dest`. Return the text."""
    name = target(dest, name)
    text = render(dest)
    out.save_text(dest, name, text)
    return text
