#!/usr/bin/env python3
"""Turn the workflow results into the catalogs every later step reads.

    python3 render.py catalogs <out>

`catalogs` reads understand_result.json and rules_result.json (as the workflows returned them), inventory.json,
fields.json, app-spec.json and overrides.json from the output folder `<out>`. It assigns stable ids through ids.json
(updated in place: existing keys keep their ids, new keys take max + 1) and writes use-cases.json, screens.json,
flows.json, rules.json and endpoints.json. It never writes ids.json's old keys away, app-spec.json or overrides.json.
Prints the counts, and any reference it could not resolve, to stderr. Exit code 2 when `<out>` is not an output
folder or understand_result.json is missing. Standard library only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out  # noqa: E402
from speclib.common import die, endpoints_match, load_json, normalize_endpoint  # noqa: E402
from speclib.ids import Registry, norm  # noqa: E402

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
        self.inventory = out.load(dest, "inventory.json", {}) or {}
        self.fields = (out.load(dest, "fields.json", {}) or {}).get("screens", [])
        self.overrides = out.load(dest, "overrides.json", {}) or {}
        self.registry = Registry(os.path.join(dest, "ids.json"))
        self.warnings = []

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
                self.warnings.append(f"screen {screen['name']} appears twice in {_path(screen.get('file'))}; the first is kept")
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
                self.warnings.append(f"inventory endpoint {e.get('type') or e.get('path')} in {_path(e.get('file'))} has "
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
        """EP ids of the inventory endpoints that the citations `METHOD /path` name."""
        found = []
        for cite in cites:
            method, _, raw = str(cite).strip().partition(" ")
            path = _endpoint_path(raw)
            hit = [eid for eid, e in endpoints.items()
                   if e["method"] == method.upper() and (e["path"] == path or endpoints_match(path, e["path"]))]
            if not hit:
                self.warnings.append(f"use case {owner} cites {cite}, which is not in the inventory")
            found += hit
        return _unique(found)

    # ------------------------------------------------------------ use cases

    def _use_cases(self, screen_ids, endpoints):
        cases = {}
        current = {norm(r["name"]) for r in self.understood.get("useCases", []) if isinstance(r, dict) and r.get("name")}
        for raw in self.understood.get("useCases", []):
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            files = sorted({_path(f) for f in _strings(raw.get("files"))})
            uid = self._use_case_id(raw["name"], files, current, cases)
            self.registry.data["UCfiles"][uid] = files
            if uid in cases:
                self.warnings.append(f"use case {raw['name']} appears twice; the first is kept")
                continue
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
                self.warnings.append(f"{where} names the screen {name}, which understand_result.json does not have")
        return _unique(ids)

    def _merge(self, cases):
        """Fold the `from` use cases of every merge override into `into`. Return the map of retired id to kept id."""
        retired = {}
        for merge in self.overrides.get("merge", []) or []:
            into = merge.get("into")
            if into not in cases:
                self.warnings.append(f"merge into {into} ignored: no such use case")
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
        for name in names:
            uid = by_name.get(norm(name))
            if uid:
                ids.append(retired.get(uid, uid))
            else:
                self.warnings.append(f"{where} names the use case {name}, which understand_result.json does not have")
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
            slug = self._element_slug(element, i)
            if slug in used:
                slug = f"{slug}-{i}"
            used.add(slug)
            element["proposedId"] = (overrides.get(f"{sid}.{slug}") or element.get("identifier")
                                     or f"{module}.{screen_slug}.{slug}")
        return elements

    def _element_slug(self, element, index):
        key = str(element.get("textKey") or "")
        slug = _slug(re.split(r"[./]", key)[-1]) if key else ""
        if not slug and element.get("text"):
            slug = "-".join(_slug(element["text"]).split("-")[:6])
        return slug or f"{element.get('kind') or 'other'}-{index}"

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
                self.warnings.append(f"flow {raw['name']} appears twice; the first is kept")
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
        for raw in self.rules_in:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            rid = self.registry.assign("RULE", self._rule_key(raw["name"], raw.get("source")))
            if rid in rules:
                self.warnings.append(f"rule {raw['name']} appears twice in {_path(raw.get('source'))}; the first is kept")
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
                      for raw in self.understood.get("useCases", []) if isinstance(raw, dict) and raw.get("name")}
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
        self.registry.save()
        return {"useCases": len(use_cases), "screens": len(screens), "flows": len(flows), "rules": len(rules),
                "endpoints": len(endpoints), "warnings": self.warnings}


def catalogs(dest):
    """Write the catalogs for the output folder `dest`. Return the counts and the unresolved references."""
    return _Catalogs(dest).run()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    cat = sub.add_parser("catalogs", help="render the catalogs from the workflow results")
    cat.add_argument("out")
    args = ap.parse_args(argv)
    if args.command == "catalogs":
        result = catalogs(args.out)
        for warning in result.pop("warnings"):
            print(f"warning: {warning}", file=sys.stderr)
        print(", ".join(f"{k} {v}" for k, v in result.items()))


if __name__ == "__main__":
    main()
