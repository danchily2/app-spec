#!/usr/bin/env python3
"""Run the stack's extractor on the app and keep what belongs to the module.

    python3 inventory.py <out>

Reads app-spec.json and module.json from the output folder `<out>` that module.py wrote. Writes inventory.json and
INVENTORY.md (App Fusion's inventory shape, only entries whose file is in the module's core or touch points, every
count with the rule that produced it), fields.json (the elements of every screen in those files) and fills the `hints`
of each shards/<id>.json with the inventory entries inside that shard. Prints the counts with their rules and the
size of fields.json. Exit code 2 when `<out>` is not an output folder that module.py wrote. Standard library only.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import android, fields, ios, out, rn  # noqa: E402
from speclib.common import die  # noqa: E402

EXTRACTORS = {"ios-native": ios, "android-native": android, "react-native": rn}
# lists of entries that name the file they come from: the only parts of the extractor result a file scope can cut
SCOPED_LISTS = ("screens", "swiftuiViews", "coordinators", "routes", "unresolvedRoutes", "navigators", "endpoints",
                "webLinks", "events", "storage")
SCOPE_RULE = "kept when its file is in the module's core or touch points"
COUNT_RULES = {  # counts this script defines itself, and the fallback for a count the extractor gives no rule
    "sourceFiles": "files of the module: its core plus its touch points",
    "stringKeys": "keys of the app's string catalog that the module's core files use",
    "routes": "distinct route names",
    "storageKeys": "storage entries",
}
OWN_COUNTS = ("sourceFiles", "stringKeys")
HINT_LISTS = ("routes", "screens", "endpoints", "events")
_LINE = re.compile(r":\d+$")


def _path(entry):
    """The file of an inventory entry without its `:line`, or None when the entry names no file."""
    value = entry.get("file") if isinstance(entry, dict) else None
    return _LINE.sub("", value) if isinstance(value, str) else None


def _distinct(entries, key):
    return len({e.get(key) for e in entries if e.get(key) is not None})


def _scoped_strings(catalog, keys):
    """The catalog cut to the module's string keys. Locales and source stay as the app has them."""
    wanted = set(keys)
    kept = dict(catalog)
    for field in ("keys", "values", "allValues"):
        if isinstance(catalog.get(field), dict):
            kept[field] = {k: v for k, v in catalog[field].items() if k in wanted}
    return kept


def _counts(inv, files):
    counts = {"sourceFiles": len(files), "stringKeys": len(inv["strings"].get("keys", {}))}
    for key in ("screens", "swiftuiViews", "coordinators", "webLinks"):
        if key in inv:
            counts[key] = len(inv[key])
    counts["routes"] = _distinct(inv["routes"], "name")
    counts["endpoints"] = _distinct(inv["endpoints"], "path")
    counts["events"] = _distinct(inv["events"], "name")
    counts["storageKeys"] = len(inv["storage"])
    return counts


def _rules(counts, extractor_rules):
    rules = {}
    for key in counts:
        if key in OWN_COUNTS:
            rules[key] = COUNT_RULES[key]
        else:
            base = extractor_rules.get(key) or f"{COUNT_RULES.get(key, key)} of the extractor"
            rules[key] = f"{base}; {SCOPE_RULE}"
    return rules


def _hint(kind, entry):
    if kind == "endpoints":
        return f"{entry['method']} {entry['path']}" if entry.get("method") else entry.get("path")
    return entry.get("name") or entry.get("path")


def _hints(inv, shard_files):
    files = set(shard_files)
    hints = {}
    for kind in HINT_LISTS:
        entries = list(inv.get(kind, [])) + (inv.get("swiftuiViews", []) if kind == "screens" else [])
        seen = []
        for entry in entries:
            value = _hint(kind, entry)
            if _path(entry) in files and value and value not in seen:
                seen.append(value)
        hints[kind] = seen
    return hints


def _render(inv, scope):
    cell = lambda v: str(v).replace("|", "/").replace("\n", " ")  # noqa: E731
    lines = [f"# Inventory of the {', '.join(scope['query'])} module" if scope["query"] else "# Inventory of the module",
             "", f"Stack {inv['stack']}. {len(scope['files'])} files: {len(scope['core'])} core, "
             f"{len(scope['files']) - len(scope['core'])} touch points. Entries outside these files are not listed.",
             "", "## Counts", "", "| Count | Value | Rule |", "| --- | --- | --- |"]
    lines += [f"| {k} | {v} | {cell(inv['rules'][k])} |" for k, v in inv["counts"].items()]
    lines += ["", "The platform section is app-wide: entitlements, URL schemes and permissions are not tied to one file.", ""]
    for title, key, columns in (("Screens", "screens", ("name", "kind", "file")),
                                ("SwiftUI views", "swiftuiViews", ("name", "file")),
                                ("Routes", "routes", ("name", "component", "file")),
                                ("Endpoints", "endpoints", ("method", "path", "raw", "file")),
                                ("Events", "events", ("name", "family", "file")),
                                ("Storage", "storage", ("kind", "key", "file"))):
        entries = inv.get(key) or []
        if not entries:
            continue
        lines += [f"## {title}", "", "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
        lines += ["| " + " | ".join(cell(e.get(c, "")) if e.get(c) is not None else "" for c in columns) + " |" for e in entries]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(dest):
    """Write inventory.json, INVENTORY.md and fields.json for the module in `dest`, fill the shard hints. Return the inventory."""
    cfg = out.load_config(dest)
    module = out.load(dest, "module.json")
    if not isinstance(module, dict) or "core" not in module:
        die(f"{dest} has no module.json (run module.py first)")
    stack = cfg["app"]["stack"]
    if stack not in EXTRACTORS:
        die(f"no extractor for stack {stack!r}")
    root = out.app_root(cfg)
    core = list(module["core"])
    files = core + [t["file"] for t in module.get("touchPoints", []) if t["file"] not in core]
    inside = set(files)

    result = EXTRACTORS[stack].extract(root)
    inv = {"version": 1, "stack": result["stack"]}
    for key in SCOPED_LISTS:
        if key in result:
            inv[key] = [e for e in result[key] if _path(e) in inside]
    for key in ("routes", "endpoints", "events", "storage"):
        inv.setdefault(key, [])
    inv["strings"] = _scoped_strings(result["strings"], module.get("stringKeys", []))
    inv["platform"] = result["platform"]
    inv["counts"] = _counts(inv, files)
    inv["rules"] = _rules(inv["counts"], result.get("rules", {}))
    out.save(dest, "inventory.json", inv)
    out.save_text(dest, "INVENTORY.md", _render(inv, {"query": cfg.get("module", {}).get("query") or [],
                                                      "files": files, "core": core}))
    out.save(dest, "fields.json", {"version": 1, "screens": fields.extract(stack, root, files)})

    for entry in module.get("shards", []):
        shard = out.load(dest, entry["file"])
        if isinstance(shard, dict):
            shard["hints"] = _hints(inv, shard.get("files", []))
            out.save(dest, entry["file"], shard)
    return inv


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0].startswith("-"):
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    inv = run(args[0])
    print(f"Inventory of {inv['stack']} app, scoped to the module")
    for key, value in inv["counts"].items():
        print(f"  {key}: {value}  rule: {inv['rules'][key]}")
    data = out.load(args[0], "fields.json", {})
    screens = data.get("screens", [])
    print(f"fields.json: {len(screens)} screens, {sum(len(s['elements']) for s in screens)} elements")
    print(f"Wrote {args[0]}: inventory.json, INVENTORY.md, fields.json, hints in shards/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
