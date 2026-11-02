#!/usr/bin/env python3
"""Turn the workflow results into the catalogs every later step reads.

    python3 render.py catalogs <out>
    python3 render.py spec <out> [--name FILE]

`catalogs` reads understand_result.json and rules_result.json (as the workflows returned them), inventory.json,
fields.json, app-spec.json and overrides.json from the output folder `<out>`. It assigns stable ids through ids.json
(updated in place: existing keys keep their ids, new keys take max + 1) and writes use-cases.json, screens.json,
flows.json, rules.json, endpoints.json and out-of-scope.json. It never writes ids.json's old keys away, app-spec.json or
overrides.json. Touch files are context, not scope: a use case whose files are all outside the core of module.json,
a rule whose source is outside it, a rule of such a use case, and the `outOfScope` lists the workflows return go to
out-of-scope.json (`{useCases, rules}` of `{id, name, reason}`), not to the catalogs.
Prints the counts, and any reference it could not resolve to stderr; writes the same warnings to render-warnings.json
as a list of `{kind, item, why}` (an empty list when there are none). An endpoint a use case cites that the inventory
does not have is kept in endpoints.json with label UNKNOWN and `inInventory: false`. Exit code 2 when `<out>` is not an output
folder or understand_result.json is missing. Standard library only.

`spec` compiles the catalogs, fields.json, inventory.json, module.json, overrides.json, ledger.json (when present) and
prose.json (when present) into the eight sections and six appendices of the template, and writes them to `<out>/FILE`
(default SPEC.md). A prose slot with no prose.json entry is written as `UNKNOWN — <what is missing>`. The output is
deterministic. Exit code 2 when `<out>` is not an output folder, a catalog is missing, or FILE leaves `<out>`.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out, spec_md  # noqa: E402
from speclib.common import die, endpoints_match, load_json, normalize_endpoint  # noqa: E402
from speclib.ids import Registry, element_slug, norm  # noqa: E402

UC_LISTS = ("personas", "permissions", "screens", "files", "endpoints", "events", "strings", "storage", "platform")
_LOCATION = re.compile(r":\d[\d,\-– ]*$")
_PARAM = re.compile(r"\{[^}]*\}|(?<=/):[A-Za-z_]\w*|(?<=/)\$[A-Za-z_]\w*")


def _path(location):
    """`rel` of a `rel:line` or `rel:line-line` location."""
    return _LOCATION.sub("", str(location or ""))


def _slug(text):
    return norm(text).replace(" ", "-")


def _unique(items):
    seen, result = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _strings(value):
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _number(entry):
    return int(entry["id"].rsplit("-", 1)[1])


def _endpoint_path(path):
    """The key form of an endpoint path: parameters of any syntax as `{}`."""
    return normalize_endpoint(path) or _PARAM.sub("{}", str(path or ""))


def _module_slug(cfg):
    query = (cfg.get("module") or {}).get("query") or []
    return (_slug(query[0]) if query else "") or "module"


class _Catalogs:
    def __init__(self, dest):
        self.dest = dest
        self.cfg = out.load_config(dest)
        self.understood = out.load(dest, "understand_result.json")
        if not isinstance(self.understood, dict):
            die(f"{dest} has no understand_result.json (run the understand workflow first)")
        rules = out.load(dest, "rules_result.json")
        self.rules_in = rules.get("rules", []) if isinstance(rules, dict) else []
        self.rules_out = (rules.get("outOfScope") or []) if isinstance(rules, dict) else []
        self.inventory = out.load(dest, "inventory.json", {}) or {}
        self.fields = (out.load(dest, "fields.json", {}) or {}).get("screens", [])
        self.overrides = out.load(dest, "overrides.json", {}) or {}
        module = out.load(dest, "module.json", {}) or {}
        self.core = {str(f) for f in module.get("core") or []} if isinstance(module, dict) else set()
        self.out_cases = []  # {id, name, reason}: use cases with no evidence in a core file
        self.out_rules = []
        self.registry = Registry(os.path.join(dest, "ids.json"))
        self.warnings = []  # the sentences, printed to stderr
        self.records = []   # the same as {kind, item, why}, written to render-warnings.json

    def _warn(self, kind, item, why):
        self.warnings.append(why)
        self.records.append({"kind": kind, "item": str(item), "why": why})

    # ------------------------------------------------------------ ids

    def _screen_key(self, name, file):
        return f"{norm(name)}|{_path(file)}"

    def _rule_key(self, name, source):
        return f"{norm(name)}|{_path(source)}"

    def _screen_ids(self):
        """Screen name to SCR ids (a name can repeat in two files), and the screen entries by id."""
        by_name, entries = {}, {}
        for screen in self.understood.get("screens", []):
            if not isinstance(screen, dict) or not screen.get("name"):
                continue
            sid = self.registry.assign("SCR", self._screen_key(screen["name"], screen.get("file")))
            if sid in entries:
                self._warn("screen", screen["name"], f"screen {screen['name']} appears twice in {_path(screen.get('file'))}; the first is kept")
                continue
            entries[sid] = screen
            by_name.setdefault(norm(screen["name"]), []).append(sid)
        return by_name, entries

    # ------------------------------------------------------------ endpoints

    def _endpoints(self):
        """One entry per inventory endpoint in scope, keyed by `METHOD path`; the entries by id."""
        entries = {}
        for e in self.inventory.get("endpoints", []):
            method = str(e.get("method") or "").upper()
            path = _endpoint_path(e.get("path"))
            if not method or not path:
                self._warn("endpoint", e.get("type") or e.get("path"),
                           f"inventory endpoint {e.get('type') or e.get('path')} in {_path(e.get('file'))} has "
                           f"no {'method' if not method else 'path'} and is left out of endpoints.json")
                continue
            eid = self.registry.assign("EP", f"{method} {path}")
            client = {"file": _path(e.get("file")), "type": e.get("type")}
            if eid in entries:
                if client not in entries[eid]["clients"]:
                    entries[eid]["clients"].append(client)
                continue
            entries[eid] = {"id": eid, "method": method, "path": path, "raw": e.get("raw"), "useCases": [],
                            "client": client, "clients": [client],
                            "request": {"fields": []}, "response": {"fields": []}, "errors": [], "auth": None,
                            "backend": None, "label": "INFERRED"}
        return entries

    def _resolve_endpoints(self, cites, endpoints, owner):
        """EP ids of the endpoints that the citations `METHOD /path` name. A citation no inventory endpoint matches is
        kept as its own entry with label `UNKNOWN`, `inInventory: false` and no client, so the spec shows it with an
        open question and the ledger counts it; a citation without a method or path is reported and left out."""
        found = []
        for cite in cites:
            method, _, raw = str(cite).strip().partition(" ")
            method, path = method.upper(), _endpoint_path(raw.strip())
            hit = [eid for eid, e in endpoints.items()
                   if e["method"] == method and (e["path"] == path or endpoints_match(path, e["path"]))]
            if not hit:
                if not method.isalpha() or not path.startswith("/"):
                    self._warn("endpoint", cite, f"use case {owner} cites {cite}, which is not an endpoint "
                                                 f"(METHOD /path) and is left out")
                    continue
                eid = self.registry.assign("EP", f"{method} {path}")
                if eid not in endpoints:
                    endpoints[eid] = {"id": eid, "method": method, "path": path, "raw": raw.strip() or None,
                                      "useCases": [], "client": None, "clients": [],
                                      "request": {"fields": []}, "response": {"fields": []}, "errors": [], "auth": None,
                                      "backend": None, "label": "UNKNOWN", "inInventory": False,
                                      "reason": f"cited by the use case {owner} but not in the inventory: no client "
                                                f"file of the module builds it"}
                self._warn("endpoint", cite, f"use case {owner} cites {cite}, which is not in the inventory; "
                                             f"kept as {eid} with label UNKNOWN")
                hit = [eid]
            found += hit
        return _unique(found)

    # ------------------------------------------------------------ use cases

    def _in_core(self, files):
        """True when one of the files is a core file, or when the core is unknown or nothing is cited."""
        files = [_path(f) for f in files if f]
        return not self.core or not files or any(f in self.core for f in files)

    def _out_of_scope(self, kind, prefix, key, name, reason):
        entry = {"id": self.registry.assign(prefix, key), "name": name, "reason": reason}
        target = self.out_cases if kind == "useCase" else self.out_rules
        if all(e["id"] != entry["id"] for e in target):
            target.append(entry)
        return entry["id"]

    def _use_cases(self, screen_ids, endpoints):
        cases = {}
        current = {norm(r["name"]) for r in self.understood.get("useCases", []) if isinstance(r, dict) and r.get("name")}
        for raw in self.understood.get("outOfScope") or []:
            if isinstance(raw, dict) and raw.get("name"):
                self._out_of_scope("useCase", "UC", norm(raw["name"]), raw["name"],
                                   raw.get("reason") or "the mapper found it only in touch files")
        for raw in self.understood.get("useCases", []):
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            files = sorted({_path(f) for f in _strings(raw.get("files"))})
            if not self._in_core(files):
                self._out_of_scope("useCase", "UC", norm(raw["name"]), raw["name"],
                                   "every file it cites is a touch file, outside the module's core")
                continue
            uid = self._use_case_id(raw["name"], files, current, cases)
            if uid in cases:
                self._warn("useCase", raw["name"], f"use case {raw['name']} appears twice; the first is kept")
                continue
            self.registry.data["UCfiles"][uid] = files  # after the duplicate check: the kept use case's files
            case = {"id": uid, "alias": None, "name": raw["name"], "description": raw.get("description", "")}
            for field in UC_LISTS:
                case[field] = _strings(raw.get(field))
            case["screens"] = self._refs(case["screens"], screen_ids, f"use case {raw['name']}")
            case["endpoints"] = self._resolve_endpoints(case["endpoints"], endpoints, raw["name"])
            case["evidence"] = raw.get("evidence") or "UNKNOWN"
            cases[uid] = case
        return cases

    def _use_case_id(self, name, files, current, cases):
        """The id of a use case: its key's id; for a new key, the id of a retired key whose recorded files are the
        same list; else a new id."""
        key = norm(name)
        if key not in self.registry.data["UC"] and files:
            live = {self.registry.data["UC"].get(k) for k in current}
            for uid, recorded in sorted(self.registry.data["UCfiles"].items()):
                if recorded == files and uid not in live and uid not in cases:
                    self.registry.adopt("UC", key, uid)
                    return uid
        return self.registry.assign("UC", key)

    def _refs(self, names, by_name, where):
        """Screen ids for screen `names`. A name no screen has is dropped and reported."""
        ids = []
        for name in names:
            hit = by_name.get(norm(name))
            if hit:
                ids.append(hit[0])
            else:
                self._warn("screen", name, f"{where} names the screen {name}, which understand_result.json does not have")
        return _unique(ids)

    def _merge(self, cases):
        """Fold the `from` use cases of every merge override into `into`. Return the map of retired id to kept id."""
        retired = {}
        for merge in self.overrides.get("merge", []) or []:
            into = merge.get("into")
            if into not in cases:
                self._warn("merge", into, f"merge into {into} ignored: no such use case")
                continue
            for src in merge.get("from", []) or []:
                if src == into or src not in cases:
                    continue
                for field in UC_LISTS:
                    cases[into][field] = _unique(cases[into][field] + cases[src][field])
                del cases[src]
                retired[src] = into
        for src, into in list(retired.items()):  # a chain of merges points at the last kept id
            while retired.get(into):
                into = retired[into]
            retired[src] = into
        return retired

    def _alias(self, cases):
        index_path = self.cfg.get("capabilityIndex")
        data = load_json(index_path) if index_path else None
        caps = data.get("capabilities") if isinstance(data, dict) else None
        if not isinstance(caps, list):
            return
        app = self.cfg["app"]["name"]
        caps = [c for c in caps if isinstance(c, dict) and c.get("id")]
        taken = set()
        ordered = sorted(cases.values(), key=_number)
        by_id = sorted(caps, key=lambda c: str(c["id"]))
        for case in ordered:  # a name match wins
            for cap in by_id:
                if cap["id"] not in taken and norm(cap.get("name")) == norm(case["name"]):
                    case["alias"] = cap["id"]
                    taken.add(cap["id"])
                    break
        pairs = []  # then the largest overlaps of implementation files, assigned globally largest first
        for case in ordered:
            if case["alias"]:
                continue
            mine = {_path(f) for f in case["files"]}
            for cap in by_id:
                impl = (cap.get("implementations") or {}).get(app) or {}
                count = len(mine & {_path(f) for f in impl.get("files") or []})
                if count and cap["id"] not in taken:
                    pairs.append((-count, _number(case), str(cap["id"]), case, cap["id"]))
        for _, _, _, case, cap_id in sorted(pairs, key=lambda p: p[:3]):
            if not case["alias"] and cap_id not in taken:
                case["alias"] = cap_id
                taken.add(cap_id)

    # ------------------------------------------------------------ screens, flows, rules

    def _use_case_ids(self, names, by_name, retired, where):
        ids = []
        outside = {e["id"] for e in self.out_cases}
        for name in names:
            uid = by_name.get(norm(name))
            if uid in outside:
                continue  # out of scope: listed in out-of-scope.json, not named by the catalogs
            if uid:
                ids.append(retired.get(uid, uid))
            else:
                self._warn("useCase", name, f"{where} names the use case {name}, which understand_result.json does not have")
        return _unique(ids)

    def _fields_for(self, screen):
        """The `fields.json` elements of the screen: same file, and same name when the file holds several screens."""
        file = _path(screen.get("file"))
        same = [s for s in self.fields if _path(s.get("file")) == file]
        named = [s for s in same if norm(s.get("screen")) == norm(screen.get("name"))]
        pick = named or (same if len(same) == 1 else [])
        return [dict(e) for s in pick for e in s.get("elements", [])]

    def _elements(self, screen, sid):
        elements = self._fields_for(screen)
        for mine in screen.get("fields") or []:  # the analysts' confirmed fields: fill gaps, add what is missing
            if not isinstance(mine, dict):
                continue
            twin = next((e for e in elements if e.get("file") == mine.get("file") and e.get("line") == mine.get("line")
                         and e.get("kind") == mine.get("kind")), None)
            if twin is None:
                elements.append({k: mine.get(k) for k in ("kind", "textKey", "text", "identifier", "file", "line")})
            else:
                for key in ("textKey", "text", "identifier"):
                    if twin.get(key) is None and mine.get(key) is not None:
                        twin[key] = mine[key]
        module, screen_slug = _module_slug(self.cfg), _slug(screen["name"])
        overrides = self.overrides.get("ids") or {}
        used = set()
        for i, element in enumerate(elements):
            name = element_slug(element, i)
            if name in used:
                name = f"{name}-{i}"
            used.add(name)
            element["proposedId"] = (overrides.get(f"{sid}.{name}") or element.get("identifier")
                                     or f"{module}.{screen_slug}.{name}")
        return elements

    def _screens(self, screen_entries, uc_by_name, retired):
        result = []
        for sid, screen in screen_entries.items():
            result.append({"id": sid, "name": screen["name"], "file": screen.get("file"),
                           "useCases": self._use_case_ids(_strings(screen.get("useCases")), uc_by_name, retired,
                                                          f"screen {screen['name']}"),
                           "actions": _strings(screen.get("actions")), "states": screen.get("states") or [],
                           "elements": self._elements(screen, sid)})
        return result

    def _flows(self, screen_by_name, uc_by_name, retired):
        flows = {}
        for raw in self.understood.get("flows", []):
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            fid = self.registry.assign("FLOW", norm(raw["name"]))
            if fid in flows:
                self._warn("flow", raw["name"], f"flow {raw['name']} appears twice; the first is kept")
                continue
            steps = []
            for step in raw.get("steps") or []:
                screen = self._refs([step.get("screen")] if step.get("screen") else [], screen_by_name, f"flow {raw['name']}")
                steps.append({"screen": screen[0] if screen else None,
                              "useCases": self._use_case_ids(_strings(step.get("useCases")), uc_by_name, retired,
                                                             f"flow {raw['name']}"),
                              "action": step.get("action")})
            flows[fid] = {"id": fid, "name": raw["name"], "persona": raw.get("persona"), "steps": steps}
        return list(flows.values())

    def _rules(self, uc_by_name, retired):
        rules = {}
        outside = {norm(e["name"]) for e in self.out_cases}
        for raw in self.rules_out:
            if isinstance(raw, dict) and raw.get("name"):
                self._out_of_scope("rule", "RULE", self._rule_key(raw["name"], raw.get("source")), raw["name"],
                                   raw.get("reason") or "the extractor found it only in touch files")
        for raw in self.rules_in:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            key = self._rule_key(raw["name"], raw.get("source"))
            if not self._in_core([raw.get("source")]):
                self._out_of_scope("rule", "RULE", key, raw["name"],
                                   f"its source {_path(raw.get('source'))} is a touch file, outside the module's core")
                continue
            if raw.get("useCase") and norm(raw["useCase"]) in outside:
                self._out_of_scope("rule", "RULE", key, raw["name"], f"its use case {raw['useCase']} is out of scope")
                continue
            rid = self.registry.assign("RULE", key)
            if rid in rules:
                self._warn("rule", raw["name"], f"rule {raw['name']} appears twice in {_path(raw.get('source'))}; the first is kept")
                continue
            name = raw.get("useCase")
            uc = self._use_case_ids([name], uc_by_name, retired, f"rule {raw['name']}")[0:1] if name else []
            rule = {"id": rid, "useCase": uc[0] if uc else None}
            for key in ("name", "category", "priority", "confidence", "plainEnglish", "given", "when", "then"):
                rule[key] = raw.get(key)
            rule["parameters"] = raw.get("parameters") or []
            rule["edgeCases"] = raw.get("edgeCases") or []
            rule["suspectedDefect"] = raw.get("suspectedDefect")
            rule["question"] = raw.get("question")
            rule["source"] = raw.get("source")
            rules[rid] = rule
        return list(rules.values())

    # ------------------------------------------------------------ labels, rename

    def _label_endpoints(self, endpoints, cases):
        for case in sorted(cases.values(), key=_number):
            files = {_path(f) for f in case["files"]}
            for eid in case["endpoints"]:
                e = endpoints[eid]
                e["useCases"].append(case["id"])
                if files & {c["file"] for c in e["clients"]}:
                    e["label"] = "VERIFIED"
        for e in endpoints.values():
            if e.get("inInventory") is False:
                continue  # cited by a use case only: no client file backs it, so it stays UNKNOWN
            if e["label"] != "VERIFIED":
                e["label"] = "UNKNOWN" if "{}" in e["path"] and not e["useCases"] else "INFERRED"

    def _rename(self, *catalogs):
        names = {r.get("id"): r.get("name") for r in self.overrides.get("rename", []) or [] if r.get("id") and r.get("name")}
        for catalog in catalogs:
            for item in catalog:
                if item["id"] in names:
                    item["name"] = names[item["id"]]

    # ------------------------------------------------------------ run

    def run(self):
        screen_by_name, screen_entries = self._screen_ids()
        endpoints = self._endpoints()
        cases = self._use_cases(screen_by_name, endpoints)
        retired = self._merge(cases)
        self._alias(cases)
        self._label_endpoints(endpoints, cases)
        uc_by_name = {norm(raw["name"]): self.registry.data["UC"][norm(raw["name"])]
                      for raw in self.understood.get("useCases", []) if isinstance(raw, dict) and raw.get("name")
                      and norm(raw["name"]) in self.registry.data["UC"]}
        screens = self._screens(screen_entries, uc_by_name, retired)
        flows = self._flows(screen_by_name, uc_by_name, retired)
        rules = self._rules(uc_by_name, retired)
        use_cases = sorted(cases.values(), key=_number)
        self._rename(use_cases, screens, flows, rules)
        out.save(self.dest, "use-cases.json", {"version": 1, "useCases": use_cases})
        out.save(self.dest, "screens.json", {"version": 1, "screens": sorted(screens, key=_number)})
        out.save(self.dest, "flows.json", {"version": 1, "flows": sorted(flows, key=_number)})
        out.save(self.dest, "rules.json", {"version": 1, "rules": sorted(rules, key=_number)})
        out.save(self.dest, "endpoints.json", {"version": 1, "endpoints": sorted(endpoints.values(), key=_number)})
        out.save(self.dest, "out-of-scope.json", {"version": 1, "useCases": sorted(self.out_cases, key=_number),
                                                  "rules": sorted(self.out_rules, key=_number)})
        out.save(self.dest, "render-warnings.json", self.records)
        self.registry.save()
        return {"useCases": len(use_cases), "screens": len(screens), "flows": len(flows), "rules": len(rules),
                "endpoints": len(endpoints), "outOfScope": len(self.out_cases) + len(self.out_rules),
                "warnings": self.warnings}


def catalogs(dest):
    """Write the catalogs for the output folder `dest`. Return the counts and the unresolved references."""
    return _Catalogs(dest).run()


def spec(dest, name="SPEC.md"):
    """Write the spec for the output folder `dest` to `name` inside it. Return its text."""
    return spec_md.write(dest, name)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalogs", help="render the catalogs from the workflow results")
    cat.add_argument("out")
    sp = sub.add_parser("spec", help="render the spec from the catalogs and prose.json")
    sp.add_argument("out")
    sp.add_argument("--name", default="SPEC.md", help="file name inside <out> (default SPEC.md)")
    args = ap.parse_args(argv)
    if args.command == "spec":
        spec(args.out, args.name)
        print(os.path.join(args.out, args.name))
        return
    if args.command == "catalogs":
        result = catalogs(args.out)
        for warning in result.pop("warnings"):
            print(f"warning: {warning}", file=sys.stderr)
        print(", ".join(f"{k} {v}" for k, v in result.items()))


if __name__ == "__main__":
    main()
