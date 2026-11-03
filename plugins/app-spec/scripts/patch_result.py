#!/usr/bin/env python3
"""Fold a partial workflow result into understand_result.json or rules_result.json.

    python3 patch_result.py <out> understand|rules PATCH [--rerun]

PATCH is a JSON file in the shape of the result it patches: a follow-up run over the shards a run returned in
`rerunShards` (pass `--rerun`), or the entries an agent corrected for one review finding. It may also hold
`"remove": [names]`.

- understand: `useCases` and `flows` are matched by normalized name, `screens` by normalized name and declaration
  file. rules: `rules` are matched by normalized name and source file. These are the keys ids.json uses, so a patched
  entry keeps its id.
- A patch entry replaces the entry with the same key, and a new key is added at the end. With `--rerun` the follow-up
  run saw other shards, so a same-key entry is merged instead: each list field (screens, files, endpoints, events,
  strings, storage, platform, permissions, states, fields ...) becomes the union of both, once each, and only the
  scalar fields are replaced. A use case never loses evidence the first run found.
- `remove` takes out every entry whose normalized name is listed, in the out-of-scope list too (names match without bracket notes or capability ids).
- `rejected`, `unverified` and `injectionFlags` are added once each. `rerunShards` is replaced when the patch has it
  (a follow-up run says which shards failed again) and kept when it does not.
- `stats` is kept, with `patches` counting the patches applied.

Run `render.py catalogs <out>` afterwards. Exit code 2 when `<out>` is not an output folder, the result to patch is
missing, or PATCH is not a JSON object. Standard library only.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out  # noqa: E402
from speclib.common import die, load_json  # noqa: E402
from speclib.ids import norm  # noqa: E402

_LINE = re.compile(r":\d[\d,\-– ]*$")


def _core(name):
    """`norm(name)` without bracket notes and capability ids, as render.py compares out-of-scope names."""
    return norm(re.sub(r"\bCAP-\d+\b", " ", re.sub(r"\([^()]*\)", " ", str(name or "")), flags=re.I))


def _file(location):
    return _LINE.sub("", str(location or ""))


KEYS = {
    "understand": {"useCases": lambda e: norm(e.get("name")),
                   "screens": lambda e: f"{norm(e.get('name'))}|{_file(e.get('file'))}",
                   "flows": lambda e: norm(e.get("name"))},
    "rules": {"rules": lambda e: f"{norm(e.get('name'))}|{_file(e.get('source'))}"},
}
FILES = {"understand": "understand_result.json", "rules": "rules_result.json"}


def _add_once(items, new):
    for item in new:
        if item not in items:
            items.append(item)
    return items


def _union(old, new):
    """`new` over `old`: a list field holds the items of both, once each, old first; any other field is `new`'s."""
    merged = dict(old)
    for k, v in new.items():
        if isinstance(v, list) and isinstance(old.get(k), list):
            items, seen = [], set()
            for x in old[k] + v:
                key = json.dumps(x, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    items.append(x)
            merged[k] = items
        else:
            merged[k] = v
    return merged


def patch(result, part, kind, rerun=False):
    """`result` with the patch `part` folded in. Return (result, replaced, added, removed). With `rerun` (a follow-up
    run over other shards) a same-key entry keeps the evidence it had: its list fields become the union."""
    gone = {norm(n) for n in part.get("remove") or [] if isinstance(n, str)}
    replaced = added = removed = 0
    for name, key in KEYS[kind].items():
        entries = [e for e in result.get(name) or [] if isinstance(e, dict)]
        before = len(entries)
        entries = [e for e in entries if norm(e.get("name")) not in gone]
        removed += before - len(entries)
        index = {key(e): i for i, e in enumerate(entries)}
        for e in part.get(name) or []:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            k = key(e)
            if k in index:
                entries[index[k]] = _union(entries[index[k]], e) if rerun else e
                replaced += 1
            else:
                index[k] = len(entries)
                entries.append(e)
                added += 1
        result[name] = entries
    # `remove` also takes an entry out of the out-of-scope list: a reviewer can say a listed neighbour is covered by
    # a kept use case or rule (names match without bracket notes or capability ids)
    if gone and isinstance(result.get("outOfScope"), list):
        names = {_core(n) for n in part.get("remove") or [] if isinstance(n, str)}
        before = len(result["outOfScope"])
        result["outOfScope"] = [o for o in result["outOfScope"]
                                if not (isinstance(o, dict) and _core(o.get("name")) in names)]
        removed += before - len(result["outOfScope"])
    for name in ("rejected", "unverified", "injectionFlags"):
        result[name] = _add_once(list(result.get(name) or []), list(part.get(name) or []))
    if isinstance(part.get("rerunShards"), list):
        result["rerunShards"] = part["rerunShards"]
    stats = result.get("stats") if isinstance(result.get("stats"), dict) else {}
    stats["patches"] = int(stats.get("patches") or 0) + 1
    result["stats"] = stats
    return result, replaced, added, removed


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    rerun = "--rerun" in args
    args = [a for a in args if a != "--rerun"]
    if len(args) != 3 or args[1] not in KEYS:
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    dest, kind, path = args
    out.load_config(dest)
    result = out.load(dest, FILES[kind])
    if not isinstance(result, dict):
        die(f"{dest} has no usable {FILES[kind]} to patch")
    part = load_json(path, None)
    if not isinstance(part, dict):
        die(f"{path} is not a JSON object in the shape of {FILES[kind]}")
    result, replaced, added, removed = patch(result, part, kind, rerun)
    out.save(dest, FILES[kind], result)
    print(f"{FILES[kind]}: {replaced} replaced, {added} added, {removed} removed; rerunShards "
          f"{result.get('rerunShards') or []}")
    print(f"Wrote {dest}: {FILES[kind]} (run render.py catalogs next)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
