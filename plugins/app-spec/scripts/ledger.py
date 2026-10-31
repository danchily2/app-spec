#!/usr/bin/env python3
"""Check that the spec covers the module's inventory, class by class.

    python3 ledger.py <out>

Compares inventory.json, fields.json and module.json with the catalogs (use-cases.json, screens.json, endpoints.json)
and overrides.json in the output folder `<out>`, and writes ledger.json and LEDGER.md. Eight classes are counted:
screens, fields, endpoints, strings, events, storage, permissions and platform. An item is covered when a catalog
entry that the spec keeps references it. An endpoint that a use case cites but the inventory lacks (`inInventory: false`
in endpoints.json) is an endpoint item too. An item that `overrides.json` drops with a reason is covered with that reason:
it is left out of the spec, listed in Appendix F and listed here. An item with no reference and no reason is listed
with `reason: null`. A class passes when covered items, with or without a reason, reach its threshold; the ledger passes
when every class passes. A class with no items passes. Thresholds come from `options.thresholds` in app-spec.json over
the defaults of DESIGN.md. Platform has no default threshold in DESIGN.md and takes 0: it is reported, never fails,
until app-spec.json sets one.

Exit code 0 when the ledger passes, 1 when it fails, 2 when `<out>` is not an output folder or a catalog is missing.
Standard library only.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render import _endpoint_path, _path  # noqa: E402
from speclib import out  # noqa: E402
from speclib.common import die  # noqa: E402
from speclib.ids import element_slug, norm  # noqa: E402

CLASSES = ("screens", "fields", "endpoints", "strings", "events", "storage", "permissions", "platform")
DEFAULT_THRESHOLDS = {"screens": 100, "endpoints": 100, "events": 100, "permissions": 100, "storage": 100,
                      "strings": 95, "fields": 95, "platform": 0}


def _list(value):
    return value if isinstance(value, list) else []


def _strings(value):
    return [v for v in _list(value) if isinstance(v, str) and v]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class _Ledger:
    def __init__(self, dest):
        self.dest = dest
        self.cfg = out.load_config(dest)
        self.inventory = _dict(out.load(dest, "inventory.json", {}))
        self.module = _dict(out.load(dest, "module.json", {}))
        self.fields = _list(_dict(out.load(dest, "fields.json", {})).get("screens"))
        overrides = _dict(out.load(dest, "overrides.json", {}))
        # the same table spec_md.Context builds: (kind, id) to the reason a person gave
        self.dropped = {(d.get("kind"), str(d["id"])): d.get("reason")
                        for d in _list(overrides.get("drop")) if isinstance(d, dict) and d.get("id")}
        self.all_cases = self._catalog("use-cases.json", "useCases")
        self.all_screens = self._catalog("screens.json", "screens")
        self.endpoints = self._catalog("endpoints.json", "endpoints")
        self.cases = [c for c in self.all_cases if (("useCase", str(c["id"])) not in self.dropped)]
        self.screens = [s for s in self.all_screens if ("screen", str(s["id"])) not in self.dropped]
        self.case_ids = {c["id"] for c in self.cases}
        self.items = {}  # kind to every item key counted: the ids `overrides.json` can drop an item by

    def _catalog(self, name, key):
        data = out.load(self.dest, name)
        if not isinstance(data, dict) or not isinstance(data.get(key), list):
            die(f"{self.dest} has no usable {name} (run render.py catalogs first)")
        return [e for e in data[key] if isinstance(e, dict) and e.get("id")]

    # ------------------------------------------------------------ counting

    def drop(self, kind, keys):
        """`(dropped, reason)` for the first of `keys` that `overrides.json` drops as `kind`. A blank reason is `None`."""
        for key in keys:
            if (kind, str(key)) in self.dropped:
                reason = self.dropped[(kind, str(key))]
                return True, (reason.strip() if isinstance(reason, str) and reason.strip() else None)
        return False, None

    def count(self, kind, rows):
        """One class. `rows` is `(item, drop keys, referenced, inherited)`: `inherited` is `(dropped, reason)` from the
        screen that holds the item, or `None`. A drop of the item itself wins over the inherited one."""
        uncovered, seen = [], set()
        for item, keys, referenced, inherited in sorted(rows, key=lambda r: r[0]):
            if item in seen:
                continue
            seen.add(item)
            dropped, reason = self.drop(kind, [*keys, item])
            if not dropped and inherited and inherited[0]:
                dropped, reason = inherited
            if dropped or not referenced:
                uncovered.append({"item": item, "reason": reason})
        self.items.setdefault(kind, set()).update(seen)
        total = len(seen)
        with_reason = sum(1 for u in uncovered if u["reason"])
        covered = total - len(uncovered) + with_reason
        return {"total": total, "covered": covered, "withReason": with_reason, "percent": _percent(covered, total),
                "uncovered": uncovered}

    # ------------------------------------------------------------ what the spec keeps

    def _kept(self, key):
        """The values of the list `key` over the use cases the spec keeps."""
        return {v for c in self.cases for v in _strings(c.get(key))}

    def _screen_for(self, name, file):
        """The `screens.json` entry for a screen of the inventory: same file, and same name when the file holds several."""
        same = [s for s in self.all_screens if _path(s.get("file")) == _path(file)]
        named = [s for s in same if norm(s.get("name")) == norm(name)]
        pick = named or (same if len(same) == 1 else [])
        return pick[0] if pick else None

    # ------------------------------------------------------------ the classes

    def screens_class(self):
        entries = [e for k in ("screens", "swiftuiViews") for e in _list(self.inventory.get(k)) if isinstance(e, dict)]
        rows = []
        for e in entries:
            name, file = e.get("name"), e.get("file")
            if not name:
                continue
            found = self._screen_for(name, file)
            item = f"{file} {name}"
            rows.append((item, [found["id"]] if found else [], found is not None, None))
        return self.count("screen", rows)

    def fields_class(self):
        element_keys = {(e.get("file"), e.get("line"), e.get("kind")) for s in self.screens
                        for e in _list(s.get("elements")) if isinstance(e, dict)}
        rows = []
        for screen in self.fields:
            if not isinstance(screen, dict):
                continue
            found = self._screen_for(screen.get("screen"), screen.get("file"))
            owner = found["id"] if found else _path(screen.get("file"))
            inherited = self.drop("screen", [found["id"]]) if found else None
            used = set()
            for i, element in enumerate(e for e in _list(screen.get("elements")) if isinstance(e, dict)):
                base = element_slug(element, i)
                name = f"{base}-{i}" if base in used else base
                used.add(name)
                referenced = (element.get("file"), element.get("line"), element.get("kind")) in element_keys
                rows.append((f"{owner}.{name}", [f"{owner}.{base}"], referenced, inherited))
        return self.count("field", rows)

    def endpoints_class(self):
        by_key = {(str(e.get("method") or "").upper(), e.get("path")): e for e in self.endpoints}
        rows = []
        for e in _list(self.inventory.get("endpoints")):
            if not isinstance(e, dict):
                continue
            method = str(e.get("method") or "").upper()
            path = _endpoint_path(e.get("path"))
            if not path:
                rows.append((f"unnamed endpoint in {_path(e.get('file'))}", [], False, None))
                continue
            entry = by_key.get((method, path)) if method else None
            used_by = set(entry.get("useCases") or []) if entry else set()
            if entry:
                used_by |= {c["id"] for c in self.cases if entry["id"] in _strings(c.get("endpoints"))}
            rows.append((f"{method} {path}" if method else path, [entry["id"]] if entry else [],
                         bool(used_by & self.case_ids), None))
        for entry in self.endpoints:  # cited by a use case but not in the inventory: a catalog item of its own
            if entry.get("inInventory") is False:
                used_by = set(entry.get("useCases") or []) | {c["id"] for c in self.cases
                                                              if entry["id"] in _strings(c.get("endpoints"))}
                rows.append((f"{str(entry.get('method') or '').upper()} {entry.get('path')}", [entry["id"]],
                             bool(used_by & self.case_ids), None))
        return self.count("endpoint", rows)

    def strings_class(self):
        inv = _dict(self.inventory.get("strings"))
        keys = _strings(self.module.get("stringKeys")) or sorted(_dict(inv.get("keys")))
        cited = self._kept("strings") | {e.get("textKey") for s in self.screens
                                         for e in _list(s.get("elements")) if isinstance(e, dict) and e.get("textKey")}
        return self.count("string", [(k, [k], k in cited, None) for k in keys])

    def events_class(self):
        names = [e.get("name") if isinstance(e, dict) else e for e in _list(self.inventory.get("events"))]
        kept = self._kept("events")
        return self.count("event", [(str(n), [str(n)], str(n) in kept, None) for n in names if n])

    def storage_class(self):
        keys = [s.get("key") or s.get("name") if isinstance(s, dict) else s for s in _list(self.inventory.get("storage"))]
        kept = self._kept("storage")
        return self.count("storage", [(str(k), [], str(k) in kept, None) for k in keys if k])

    def permissions_class(self):
        names = [p.get("key") or p.get("name") if isinstance(p, dict) else p
                 for p in _list(_dict(self.inventory.get("platform")).get("permissions"))]
        kept = {norm(v) for v in self._kept("permissions")}
        return self.count("permission", [(str(n), [], norm(n) in kept, None) for n in names if n])

    def platform_class(self):
        """Every other entry of the platform section as `<section>:<value>`; a use case cites the whole item or the value."""
        kept = {norm(v) for v in self._kept("platform")}
        rows = []
        for section, value in sorted(_dict(self.inventory.get("platform")).items()):
            if section == "permissions":
                continue
            for part in _platform_values(value):
                item = f"{section}:{part}" if part else section
                rows.append((item, [section], norm(item) in kept or bool(part and norm(part) in kept), None))
        return self.count("platform", rows)

    def thresholds(self):
        configured = _dict(_dict(self.cfg.get("options")).get("thresholds"))
        return {c: configured[c] if _number(configured.get(c)) else DEFAULT_THRESHOLDS[c] for c in CLASSES}

    def run(self):
        thresholds = self.thresholds()
        classes = {c: getattr(self, f"{c}_class")() for c in CLASSES}
        for name, cls in classes.items():
            cls["pass"] = cls["total"] == 0 or cls["covered"] * 100 >= thresholds[name] * cls["total"]
        # key order of the file: total, covered, withReason, percent, pass, uncovered
        classes = {n: {k: c[k] for k in ("total", "covered", "withReason", "percent", "pass", "uncovered")}
                   for n, c in classes.items()}
        return {"version": 1, "classes": classes, "thresholds": thresholds,
                "pass": all(c["pass"] for c in classes.values())}


def _percent(covered, total):
    if not total:
        return 100
    value = round(covered * 100 / total, 1)
    return int(value) if value == int(value) else value


def _platform_values(value):
    """The parts of one platform entry that name an item: a list gives each of its members, a flag the entry itself."""
    if isinstance(value, bool):
        return [""] if value else []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, dict):
        return [str(k) for k in sorted(value)]
    parts = []
    for v in _list(value):
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, dict):
            parts.append(str(v.get("key") or v.get("name") or v.get("id") or json.dumps(v, sort_keys=True, ensure_ascii=False)))
        elif v is not None:
            parts.append(str(v))
    return [p for p in parts if p]


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_md(led):
    lines = ["# Coverage ledger", "", f"Result: {'pass' if led['pass'] else 'fail'}", "",
             "| Class | Total | Covered | With reason | Uncovered | Percent | Threshold | Pass |",
             "|---|---|---|---|---|---|---|---|"]
    for name, c in led["classes"].items():
        row = [name, c["total"], c["covered"], c["withReason"], c["total"] - c["covered"], c["percent"],
               led["thresholds"][name], "pass" if c["pass"] else "fail"]
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    for name, c in led["classes"].items():
        if c["uncovered"]:
            lines += ["", f"## Uncovered {name}", ""]
            lines += [f"- `{_cell(u['item'])}`: {_cell(u['reason']) if u['reason'] else 'no reason'}" for u in c["uncovered"]]
    return "\n".join(lines) + "\n"


def compute(dest):
    """Count the coverage of the output folder `dest`, write ledger.json and LEDGER.md, return the ledger."""
    led = _Ledger(dest).run()
    out.save(dest, "ledger.json", led)
    out.save_text(dest, "LEDGER.md", render_md(led))
    return led


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: ledger.py <out>", file=sys.stderr)
        return 2
    led = compute(args[0])
    print(f"Ledger: {'pass' if led['pass'] else 'fail'}")
    for name, c in led["classes"].items():
        print(f"  {name}: {c['covered']}/{c['total']} ({c['percent']}%, threshold {led['thresholds'][name]}%) "
              f"{'pass' if c['pass'] else 'fail'}")
    print(f"Wrote {args[0]}: ledger.json, LEDGER.md")
    return 0 if led["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
