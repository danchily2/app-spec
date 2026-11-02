#!/usr/bin/env python3
"""Merge what the contract reader returned into endpoints.json.

    python3 merge_contracts.py <out> [ENVELOPE ...]

Each ENVELOPE is a JSON file in the contract reader's envelope shape:

    {"endpoints": [{"id", "request", "response", "errors", "auth", "label", "reason", "citations"}],
     "disagreements": [{"endpoint", "field", "client", "backend", "note"}],
     "injectionFlags": ["file:line: ..."]}

Every string of an envelope is first rewritten so its citations are relative to the app root or a contract root: an
absolute root and a leading `<root folder name>/` are stripped. The envelopes are then folded into `<out>/contracts_result.json` (an entry with the same id replaces the earlier one,
disagreements and flags are added once), and then contracts_result.json is applied to endpoints.json. Without an
ENVELOPE the saved contracts_result.json is applied again: run it after every `render.py catalogs` and `contracts.py`,
because `render.py catalogs` writes endpoints.json from scratch.

The merge rule, applied to each endpoint the reader returned, matched by id:
- `request`, `response`, `errors` and `auth` are written from the reader when the reader gives them.
- The reader's disagreements for the endpoint are added to its `disagreements` list, once each.
- The label: a `VERIFIED` label (set by contracts.py) stays `VERIFIED`, unless the reader returns `UNKNOWN` with a
  `reason` that states which field it could not read (the reason says "field", or names a request or response field
  of the entry after the merge); then it becomes `UNKNOWN` and the reason is kept as `reason`. Any
  other label can go down to the reader's label, and goes up only from `UNKNOWN` to `INFERRED` (the reader found the
  client). The reader never makes an endpoint `VERIFIED`: that needs the backend route contracts.py found.
- An id that endpoints.json does not hold is reported on stderr and skipped.

Prints one line per endpoint changed and every injection flag. Exit code 2 when `<out>` is not an output folder,
endpoints.json is missing, or an envelope is not valid JSON in this shape. Standard library only.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out, paths  # noqa: E402
from speclib.common import die, load_json  # noqa: E402

RESULT = "contracts_result.json"
LABELS = ("UNKNOWN", "INFERRED", "VERIFIED")
FIELDS = ("request", "response", "errors", "auth")
DISAGREEMENT_KEYS = ("field", "client", "backend", "note")


def _envelope(path, root_list=()):
    data = load_json(path, None)
    if not isinstance(data, dict) or not isinstance(data.get("endpoints", []), list):
        die(f"{path} is not a contract reader envelope (a JSON object with an endpoints list)")
    data = paths.relativize(data, list(root_list))
    return {
        "endpoints": [e for e in data.get("endpoints") or [] if isinstance(e, dict) and e.get("id")],
        "disagreements": [d for d in data.get("disagreements") or [] if isinstance(d, dict) and d.get("endpoint")],
        "injectionFlags": [str(f) for f in data.get("injectionFlags") or [] if f],
    }


def _add_once(items, new):
    for item in new:
        if item not in items:
            items.append(item)
    return items


def fold(saved, envelope):
    """`saved` with `envelope` folded in: same id replaces, disagreements and flags added once."""
    by_id = {e["id"]: e for e in saved.get("endpoints") or []}
    for e in envelope["endpoints"]:
        by_id[e["id"]] = e
    return {"version": 1,
            "endpoints": [by_id[k] for k in sorted(by_id)],
            "disagreements": _add_once(list(saved.get("disagreements") or []), envelope["disagreements"]),
            "injectionFlags": _add_once(list(saved.get("injectionFlags") or []), envelope["injectionFlags"])}


def label(old, new, reason):
    """The merged label of an endpoint whose label was `old` when the reader returned `new` with `reason`."""
    if new not in LABELS:
        return old
    if old == "VERIFIED":
        return "UNKNOWN" if new == "UNKNOWN" and reason else "VERIFIED"
    if old not in LABELS:
        return "INFERRED" if new == "VERIFIED" else new
    if old == "UNKNOWN":
        return "INFERRED" if new in ("INFERRED", "VERIFIED") else "UNKNOWN"
    return new if LABELS.index(new) < LABELS.index(old) else old


def names_a_field(reason, entry):
    """True when `reason` is field-level: it says "field", or names a request or response field of `entry`."""
    if not isinstance(reason, str) or not reason.strip():
        return False
    if re.search(r"\bfields?\b", reason, re.I):
        return True
    names = {f.get("name") for key in ("request", "response") for f in ((entry.get(key) or {}).get("fields") or [])
             if isinstance(f, dict) and isinstance(f.get("name"), str) and f.get("name")}
    return any(re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", reason) for n in names)


def apply(dest, result):
    """Apply `result` (the contracts_result.json shape) to endpoints.json in `dest`. Return (changed ids, unknown ids)."""
    data = out.load(dest, "endpoints.json")
    if not isinstance(data, dict) or not isinstance(data.get("endpoints"), list):
        die(f"{dest} has no usable endpoints.json (run render.py catalogs first)")
    entries = {e.get("id"): e for e in data["endpoints"] if isinstance(e, dict)}
    changed, unknown = [], []
    for read in result.get("endpoints") or []:
        entry = entries.get(read["id"])
        if entry is None:
            unknown.append(read["id"])
            continue
        before = json.dumps(entry, sort_keys=True)
        for key in FIELDS:
            if read.get(key) is not None:
                entry[key] = read[key]
        reason = read.get("reason") if names_a_field(read.get("reason"), entry) else None
        entry["label"] = label(entry.get("label"), read.get("label"), reason)
        if entry["label"] == "UNKNOWN" and reason:
            entry["reason"] = reason.strip()
        own = [{k: d.get(k) for k in DISAGREEMENT_KEYS} for d in result.get("disagreements") or []
               if d.get("endpoint") == read["id"]]
        if own:
            entry["disagreements"] = _add_once(list(entry.get("disagreements") or []), own)
        if json.dumps(entry, sort_keys=True) != before:
            changed.append(read["id"])
    out.save(dest, "endpoints.json", data)
    return changed, unknown


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0].startswith("-"):
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    dest, envelopes = args[0], args[1:]
    root_list = paths.roots(out.load_config(dest))
    saved = out.load(dest, RESULT, {}) or {}
    saved = saved if isinstance(saved, dict) else {}
    for path in envelopes:
        saved = fold(saved, _envelope(path, root_list))
    if envelopes:
        out.save(dest, RESULT, saved)
    if not saved.get("endpoints"):
        print(f"no contract reader result in {dest}; endpoints.json is unchanged")
        return 0
    changed, unknown = apply(dest, saved)
    by_id = {e["id"]: e for e in out.load(dest, "endpoints.json")["endpoints"] if isinstance(e, dict)}
    for ident in changed:
        print(f"{ident}: merged, label {by_id[ident].get('label')}")
    for ident in unknown:
        print(f"{ident}: not in endpoints.json, skipped", file=sys.stderr)
    for flag in saved.get("injectionFlags") or []:
        print(f"injection flag: {flag}")
    print(f"Wrote {dest}: endpoints.json" + (f", {RESULT}" if envelopes else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
