#!/usr/bin/env python3
"""Resolve the module to specify, find its touch points and split it into shards.

    python3 module.py <app> --module <name|path> [--module ...] --out DIR [--app-name NAME] [--contracts REPO ...]
                      [--max-lines N] [--confirmed] [--locale CODE]

A --module value is a folder name (matched against package roots: Swift packages, Gradle modules, React Native screen
and feature folders), or a folder or glob inside the app. Writes app-spec.json (a re-run updates the fields this script owns in place),
module.json and shards/<id>.json (one file per shard, hints empty until inventory.py fills them). Exit code 2 when a
name matches no folder or several unrelated folders. Standard library only.
"""

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import detect, out, strings, touchpoints  # noqa: E402
from speclib.common import die, git_info, now_iso, read_text, strip_comments, walk  # noqa: E402

DEFAULT_MAX_LINES = 9000
MERGE_BELOW = 300  # groups under this many lines share a shard with their neighbours
EMPTY_HINTS = ("routes", "screens", "endpoints", "events")
# words that mark a folder as the same module as its bare-name neighbour: Payslips, PayslipsFeature, payslips-api
MODULE_SUFFIXES = ("feature", "interface", "module", "kit", "core", "services", "service", "api", "ui", "screens",
                   "screen", "impl", "lib")
AREA_MARKERS = {"Sources", "src", "java", "kotlin"}
CATALOG_RN_DIRS = ["src", "app", "assets", "locales", "translations"]
DEFAULTS = {
    "passes": 2,
    "thresholds": {"screens": 100, "endpoints": 100, "events": 100, "permissions": 100, "storage": 100,
                   "strings": 95, "fields": 95},
    "bannedNouns": ["Realm", "Swinject", "NotificationCenter", "ViewModel", "Redux", "Hilt", "Room"],
}


# ---------------------------------------------------------------- folders

def _index(app_root):
    """Every file of the app (relative paths) and every folder above one."""
    files = [rel for rel, _ in walk(app_root)]
    dirs = set()
    for rel in files:
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return files, dirs


def package_roots(stack, files, dirs):
    """Folders that are a unit of the app's own structure for this stack."""
    names = {}
    for rel in files:
        folder, _, name = rel.rpartition("/")
        names.setdefault(folder, set()).add(name)
    roots = set()
    if stack == "ios-native":
        roots |= {d for d in dirs if "Package.swift" in names.get(d, ())}
        roots |= {d[: -len("/Sources")] for d in dirs if d.endswith("/Sources")}
    elif stack == "android-native":
        roots |= {d for d in dirs if names.get(d, set()) & {"build.gradle", "build.gradle.kts"}}
    elif stack == "react-native":
        roots |= {d for d in dirs if re.fullmatch(r"src/(?:screens|features)/[^/]+", d)}
    return roots


def _topmost(folders):
    """The folders that are not inside another one of the list, sorted."""
    folders = sorted(set(folders))
    return [f for f in folders if not any(f.startswith(g + "/") for g in folders if g != f)]


def _inside(rel, folders):
    return any(rel == f or rel.startswith(f + "/") for f in folders)


def _loc(path):
    text = read_text(path)
    return 0 if text is None else sum(1 for line in text.splitlines() if line.strip())


def files_under(app_root, stack, folders):
    """Source files, tests left out, under any of the folders. Relative paths in path order."""
    return [rel for rel, _ in walk(app_root, touchpoints.source_exts(stack), include_tests=False)
            if _inside(rel, folders)]


def _folder_summary(app_root, stack, folder):
    files = files_under(app_root, stack, [folder])
    return {"folder": folder, "files": len(files), "loc": sum(_loc(os.path.join(app_root, f)) for f in files)}


def resolve_by_name(app_root, stack, names):
    """Folders whose last component contains one of the names, case-insensitively.

    `core` holds the matching package roots. `candidates` holds other matching folders with source files, for an app
    whose structure the stack rules do not recognise."""
    files, dirs = _index(app_root)
    wanted = [n.lower() for n in names if n]

    def matches(folder):
        last = folder.rsplit("/", 1)[-1].lower()
        return any(n in last for n in wanted)

    roots = package_roots(stack, files, dirs)
    core = _topmost(d for d in roots if matches(d))
    with_source = {os.path.dirname(rel) for rel, _ in walk(app_root, touchpoints.source_exts(stack), include_tests=False)}
    with_source = {d for s in with_source for d in _ancestors(s)}
    candidates = _topmost(d for d in with_source if d not in roots and matches(d) and not _inside(d, core))
    return {"core": core, "candidates": [_folder_summary(app_root, stack, d) for d in candidates]}


def _ancestors(folder):
    parts = folder.split("/") if folder else []
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def resolve_by_paths(app_root, paths):
    """Explicit folders or globs inside the app. Anything that resolves outside the app, or to a file, is dropped."""
    root = os.path.realpath(app_root)
    found = []
    for raw in paths:
        pattern = raw if os.path.isabs(raw) else os.path.join(root, raw)
        hits = glob.glob(pattern, recursive=True) if glob.has_magic(raw) else [pattern]
        for hit in hits:
            real = os.path.realpath(hit)
            if os.path.isdir(real) and real != root and real.startswith(root + os.sep):
                found.append(os.path.relpath(real, root).replace(os.sep, "/"))
    return {"core": _topmost(found), "candidates": []}


def _base(folder):
    """The module a folder belongs to: its last component without separators and without a role suffix."""
    base = re.sub(r"[^a-z0-9]", "", folder.rsplit("/", 1)[-1].lower())
    changed = True
    while changed:
        changed = False
        for suffix in MODULE_SUFFIXES:
            if base.endswith(suffix) and len(base) - len(suffix) >= 3:
                base, changed = base[: -len(suffix)], True
    return base


def _is_path(app_root, value):
    return glob.has_magic(value) or "/" in value or os.path.isabs(value) or os.path.isdir(os.path.join(app_root, value))


def resolve_module(app_root, stack, query):
    """The core folders for the --module values. Exit 2 when a name matches nothing or several modules."""
    core = []
    for item in query:
        if _is_path(app_root, item):
            folders = resolve_by_paths(app_root, [item])["core"]
            if not folders:
                die(f"no folder matches {item}")
        else:
            found = resolve_by_name(app_root, stack, [item])
            folders = found["core"] or [c["folder"] for c in found["candidates"]]
            if not folders:
                die(f"no folder matches {item}")
            if len({_base(f) for f in folders}) > 1:
                die(f"several folders match {item}: {', '.join(folders)}")
        core += folders
    return _topmost(core)


# ---------------------------------------------------------------- strings

def load_catalog(app_root, stack):
    """The app's string catalog in the shape of speclib.strings."""
    root = os.path.realpath(app_root)
    if stack == "ios-native":
        files = [rel for rel, _ in walk(root, {".xcstrings", ".strings"})]
        return strings.combine(strings.parse_xcstrings(root, [f for f in files if f.endswith(".xcstrings")]),
                               strings.parse_lproj_strings(root, [f for f in files if f.endswith(".strings")]))
    if stack == "android-native":
        files = [rel for rel, _ in walk(root, {".xml"}) if "/res/values" in "/" + rel]
        return strings.combine(strings.parse_android_strings(root, files))
    if stack == "react-native":
        return strings.combine(strings.find_i18n_json(root, include=CATALOG_RN_DIRS))
    return strings.combine()


def string_keys_for(core_files, catalog, app_root=None):
    """The catalog keys the core files use, sorted. Paths are read as given, or under `app_root` when it is set."""
    known = set((catalog or {}).get("keys") or {})
    used = set()
    for path in core_files:
        text = read_text(os.path.join(app_root, path) if app_root else path)
        if text:
            used |= touchpoints.string_literals(strip_comments(text)) & known
    return sorted(used)


# ---------------------------------------------------------------- shards

def _area(rel):
    """The area of the app a file belongs to: the folder above Sources, src or java, else the top folder."""
    dirs = rel.split("/")[:-1]
    if not dirs:
        return "(root)", ""
    for i, part in enumerate(dirs):
        if i >= 1 and part in AREA_MARKERS:
            return "/".join(dirs[:i]), "/".join(dirs[:i])
    return dirs[0], dirs[0]


def _chunk(name, files, max_lines):
    """Fill shards of at most max_lines in path order. A file longer than max_lines gets a shard of its own."""
    parts, current = [], {}
    for rel, loc in sorted(files.items()):
        if current and sum(current.values()) + loc > max_lines:
            parts.append(current)
            current = {}
        current[rel] = loc
    if current:
        parts.append(current)
    return [(name if len(parts) == 1 else f"{name}#{i}", part) for i, part in enumerate(parts, 1)]


def _split(name, prefix, files, max_lines):
    """Cut one area into parts of at most max_lines: by sub-folder, then by file order inside a folder."""
    if sum(files.values()) <= max_lines:
        return [(name, files)]
    subs, direct = {}, {}
    for rel, loc in files.items():
        rest = rel[len(prefix) + 1:] if prefix else rel
        if "/" in rest:
            subs.setdefault(rest.split("/", 1)[0], {})[rel] = loc
        else:
            direct[rel] = loc
    parts = []
    for head, sub in sorted(subs.items()):
        parts += _split(f"{name}/{head}", f"{prefix}/{head}" if prefix else head, sub, max_lines)
    if direct:
        parts += _chunk(f"{name}/(top)" if subs else name, direct, max_lines)
    return parts


def _pack(parts, max_lines):
    """Merge neighbouring parts under MERGE_BELOW lines, in name order, into shards of at most max_lines."""
    packed, names, current = [], [], {}
    for name, files in sorted(parts, key=lambda p: p[0].lower()):
        size = sum(files.values())
        if size >= MERGE_BELOW:
            packed.append((name, files))
            continue
        if current and sum(current.values()) + size > max_lines:
            packed.append((_pack_name(names), current))
            names, current = [], {}
        names.append(name)
        current.update(files)
    if current:
        packed.append((_pack_name(names), current))
    return packed


def _pack_name(names):
    return names[0] if len(names) == 1 else f"[{names[0]}..{names[-1]}]"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:48] or "root"


def make_shards(app_root, files, kind, max_lines=DEFAULT_MAX_LINES):
    """Split files into shards an analyst can read in full. Ids are `<kind>-<slug>`.

    Files are grouped by area, areas over max_lines are split by sub-folder, and small groups are merged. No file is
    dropped. A single file longer than max_lines is the one case where a shard is over the limit."""
    sized = {}
    for rel in files:
        sized[rel] = _loc(os.path.join(app_root, rel))
    areas = {}
    for rel, loc in sized.items():
        name, prefix = _area(rel)
        areas.setdefault((name, prefix), {})[rel] = loc
    parts = []
    for (name, prefix), group in sorted(areas.items()):
        parts += _split(name, prefix, group, max_lines)
    shards, seen = [], {}
    for name, group in _pack(parts, max_lines):
        slug = _slug(name.split("..")[0])  # a merged shard is named after its first part
        seen[slug] = seen.get(slug, 0) + 1
        suffix = "" if seen[slug] == 1 else f"-{seen[slug]}"
        shards.append({"id": f"{kind}-{slug}{suffix}", "kind": kind, "name": name, "files": sorted(group),
                       "loc": sum(group.values()), "hints": {k: [] for k in EMPTY_HINTS}})
    return shards


# ---------------------------------------------------------------- command line

def _config(args, root, stack, contracts):
    git = git_info(root)
    return {
        "version": 1,
        "app": {"path": root, "name": args.app_name or os.path.basename(root), "stack": stack, "commit": git["commit"],
                "branch": git["branch"], "clean": git["clean"]},
        "module": {"query": list(args.module), "confirmed": bool(args.confirmed)},
        "contracts": contracts,
        "capabilityIndex": None,
        "scope": None,
        "options": {"passes": DEFAULTS["passes"], "locale": args.locale or "en", "thresholds": dict(DEFAULTS["thresholds"]),
                    "bannedNouns": list(DEFAULTS["bannedNouns"])},
        "created": now_iso().replace("+00:00", "Z"),
    }


def _update_config(cfg, args, root, contracts):
    """A re-run: set the fields this script owns, keep every other field as it is."""
    git = git_info(root)
    app = cfg.setdefault("app", {})
    app.update({"commit": git["commit"], "branch": git["branch"], "clean": git["clean"]})
    module = cfg.setdefault("module", {})
    module["query"] = list(args.module)
    if args.confirmed:
        module["confirmed"] = True
    module.setdefault("confirmed", False)
    cfg["contracts"] = contracts
    cfg["capabilityIndex"] = None
    cfg["scope"] = None
    if args.locale:
        cfg.setdefault("options", {})["locale"] = args.locale
    return cfg


def _contracts(paths):
    found = []
    for path in paths or []:
        real = os.path.realpath(path)
        if not os.path.isdir(real):
            die(f"contract repository {path} is not a folder")
        found.append({"path": real, "name": os.path.basename(real), "commit": git_info(real)["commit"]})
    return found


def _write_shards(dest, shards):
    folder = os.path.join(dest, "shards")
    if os.path.isdir(folder):  # a re-run regenerates the shards, so ids of an earlier run must not linger
        for name in os.listdir(folder):
            if name.endswith(".json"):
                os.remove(os.path.join(folder, name))
    entries = []
    for shard in shards:
        out.save(dest, f"shards/{shard['id']}.json", shard)
        entries.append({k: shard[k] for k in ("id", "kind", "name", "files", "loc")})
        entries[-1]["file"] = f"shards/{shard['id']}.json"
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("app")
    ap.add_argument("--module", action="append", required=True, help="a folder name, folder or glob; repeat for several")
    ap.add_argument("--out", required=True)
    ap.add_argument("--app-name", help="short name of the app, used in header lines (default: the app folder's name)")
    ap.add_argument("--contracts", nargs="*", default=[], metavar="REPO", help="backend repositories read as contracts")
    ap.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    ap.add_argument("--confirmed", action="store_true", help="a person confirmed the proposed scope")
    ap.add_argument("--locale", help="source-language code of the strings (default en; a re-run keeps the stored one)")
    args = ap.parse_args(argv)
    if args.max_lines < 1:
        die("--max-lines must be at least 1")
    root = os.path.realpath(args.app)
    if not os.path.isdir(root):
        die(f"{args.app} is not a folder")
    dest = os.path.realpath(args.out)
    if dest == root or dest.startswith(root + os.sep):
        die(f"--out {args.out} is inside the app; write the output folder outside it")
    stack = detect.detect(root)["stack"]

    core_folders = resolve_module(root, stack, args.module)
    core_files = files_under(root, stack, core_folders)
    if not core_files:
        die(f"no source files under {', '.join(core_folders)}")
    keys = string_keys_for(core_files, load_catalog(root, stack), root)
    touch = touchpoints.find(root, stack, core_files, keys)
    shards = make_shards(root, core_files, "core", args.max_lines)
    shards += make_shards(root, [t["file"] for t in touch], "touch", args.max_lines)

    contracts = _contracts(args.contracts)
    updated = os.path.isfile(os.path.join(dest, out.CONFIG))
    out.save(dest, out.CONFIG, _update_config(out.load_config(dest), args, root, contracts) if updated
             else _config(args, root, stack, contracts))
    entries = _write_shards(dest, shards)
    total = sum(s["loc"] for s in shards)
    out.save(dest, "module.json", {"version": 1, "core": core_files, "touchPoints": touch, "stringKeys": keys,
                                   "shards": entries, "loc": total})

    print(f"Module {', '.join(args.module)} in {os.path.basename(root)} ({stack})")
    print("Core folders:")
    for folder in core_folders:
        info = _folder_summary(root, stack, folder)
        print(f"  {folder}  ({info['files']} files, {info['loc']} lines)")
    print(f"Touch points: {len(touch)}")
    for t in touch:
        print(f"  {t['file']}  {t['reason']}")
    print(f"String keys: {len(keys)}")
    print(f"Shards: {len(shards)} ({sum(1 for s in shards if s['kind'] == 'core')} core, "
          f"{sum(1 for s in shards if s['kind'] == 'touch')} touch), {total} lines")
    print(f"Wrote {dest}: " + ("updated app-spec.json, " if updated else "app-spec.json, ")
          + "module.json, shards/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
