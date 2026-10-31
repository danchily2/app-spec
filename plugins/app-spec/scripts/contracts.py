#!/usr/bin/env python3
"""Find the backend route of each endpoint of the module and record it.

    python3 contracts.py <out> [--repo PATH ...] [--framework auto|aspnet|express]

Reads endpoints.json (written by render.py catalogs) from the output folder `<out>` and, for each endpoint, looks for
a route with the same method and path in a contract repository. A match fills `backend` (the repository's name, file,
line, authorization) and an unmatched endpoint keeps `backend` null. The name is the `name` of the matching entry in the
`contracts` list of app-spec.json, else the repository folder's name: an absolute path stays in app-spec.json only, so
the spec never shows a home folder. Without --repo, every repository in the `contracts`
list of app-spec.json is read, one after the other. A later repository never clears or replaces a match an earlier one
made, and a second run gives the same file. Backend files are read, never executed or written. Standard library only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out  # noqa: E402
from speclib.common import (SOURCE_EXT, die, endpoints_match, line_of, match_brace, normalize_endpoint,  # noqa: E402
                            read_text, strip_comments, walk)

VERBS = ("get", "post", "put", "delete", "patch", "head", "options")
_NEST_AUTH = re.compile(r"@UseGuards\(\s*([A-Za-z0-9_]+)")


# ---------------------------------------------------------------- shared helpers

def _join(prefix, suffix):
    """Join two route parts into one absolute path. A suffix starting with `~/` or `/` ignores the prefix."""
    if suffix is not None and suffix.startswith(("~/", "/")):
        return "/" + suffix.lstrip("~").strip("/")
    parts = [p.strip("/") for p in (prefix, suffix) if p and p.strip("/")]
    return "/" + "/".join(parts)


def _files(repo_root, exts):
    for rel, full in walk(repo_root, exts, include_tests=False):
        text = read_text(full)
        if text is not None:
            yield rel, strip_comments(text)


# ---------------------------------------------------------------- ASP.NET

_CLASS = re.compile(r"\bclass\s+(\w+)")
_SIGNATURE = re.compile(
    r"^[ \t]*(?:public|protected|internal)\s+(?:(?:async|virtual|override|static)\s+)*([\w<>\[\],.?\s]+?)\s+(\w+)\s*(?:<[^>(]*>)?\(",
    re.M)
_MODIFIERS = re.compile(r"(?:\b(?:public|internal|sealed|abstract|partial|static)\s+)+$")
_ATTRS_BEFORE = re.compile(r"((?:\s*\[(?:[^\[\]]|\[[^\]]*\])*\])+)\s*$")
_ASP_VERB = re.compile(r"\[\s*Http(Get|Post|Put|Delete|Patch|Head|Options)\b(?:\(\s*(?:Template\s*=\s*)?\"([^\"]*)\")?")
_ROUTE = re.compile(r"\[\s*Route\(\s*\"([^\"]*)\"")
_AUTHORIZE = re.compile(r"\[\s*Authorize\b(?:\(([^\]]*)\))?\s*\]")
_ASP_POLICY = re.compile(r"Policy\s*=\s*\"([^\"]*)\"")
_ASP_ROLES = re.compile(r"Roles\s*=\s*\"([^\"]*)\"")
_PRIMITIVES = {"string", "int", "long", "bool", "guid", "datetime", "decimal", "double", "float", "short", "byte",
               "cancellationtoken", "char", "object", "datetimeoffset", "dateonly", "timeonly", "uint", "ulong"}


def _attrs_before(text):
    """The run of attributes that ends `text`, as a match (looks back at most 2000 characters)."""
    return _ATTRS_BEFORE.search(text[-2000:])


def _split_top(text):
    """Split on commas that sit outside <>, () and []."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "<([":
            depth += 1
        elif ch in ">)]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _unwrap(type_text):
    """T from Task<ActionResult<T>>, ActionResult<T> or Task<T>. None for IActionResult and void."""
    t = " ".join(type_text.split())
    for wrapper in ("Task", "ValueTask", "ActionResult"):
        m = re.fullmatch(wrapper + r"\s*<(.*)>", t)
        if m:
            return _unwrap(m.group(1))
    if t in ("IActionResult", "ActionResult", "void", "Task", "ValueTask", "IResult", ""):
        return None
    return t


def _aspnet_auth(attrs):
    m = _AUTHORIZE.search(attrs)
    if not m:
        return None
    args = m.group(1) or ""
    policy, roles = _ASP_POLICY.search(args), _ASP_ROLES.search(args)
    if policy:
        return policy.group(1)
    return f"Roles: {roles.group(1)}" if roles else "Authorize"


def _aspnet_request_type(params_text, template):
    in_route = set(re.findall(r"\{\*?(\w+)", template or ""))
    for param in _split_top(params_text):
        bare = re.sub(r"\[[^\]]*\]\s*", "", param)
        bare = re.sub(r"\s*=.*$", "", bare).strip()
        tokens = bare.rsplit(None, 1)
        if len(tokens) != 2 or tokens[1] in in_route:
            continue
        type_name = tokens[0].replace("this ", "").strip()
        if type_name.rstrip("?").lower() in _PRIMITIVES:
            continue
        return type_name
    return None


def _aspnet_routes(repo_root):
    routes = []
    for rel, text in _files(repo_root, {".cs"}):
        for cm in _CLASS.finditer(text):
            open_i = text.find("{", cm.end())
            if open_i < 0:
                continue
            close_i = match_brace(text, open_i)
            if close_i < 0:
                continue
            head = _attrs_before(_MODIFIERS.sub("", text[:cm.start()]))
            class_attrs = head.group(1) if head else ""
            route = _ROUTE.search(class_attrs)
            name = cm.group(1)
            controller = name[:-len("Controller")] if name.endswith("Controller") else name
            prefix = route.group(1).replace("[controller]", controller) if route else ""
            class_auth = _aspnet_auth(class_attrs)
            body = text[open_i:close_i]
            for sm in _SIGNATURE.finditer(body):
                before = _attrs_before(body[:sm.start()])
                if not before:
                    continue
                attrs = before.group(1)
                verb = _ASP_VERB.search(attrs)
                if not verb:
                    continue
                params_open = sm.end() - 1
                params_close = match_brace(body, params_open, "(", ")")
                params = body[params_open + 1:params_close] if params_close > 0 else ""
                template = verb.group(2)
                path = _join(prefix, template)
                # the line of the verb attribute: the start of the attribute block plus the lines before the verb
                verb_index = open_i + before.start(1) + verb.start()
                routes.append({
                    "method": verb.group(1).upper(), "path": path, "file": rel, "line": line_of(text, verb_index),
                    "auth": _aspnet_auth(attrs) or class_auth,
                    "requestType": _aspnet_request_type(params, f"{prefix}/{template or ''}"),
                    "responseType": _unwrap(sm.group(1)),
                })
    return routes


# ---------------------------------------------------------------- Express and NestJS

_EXPRESS = re.compile(
    r"\b(?:router|app|route|routes|server|\w+Router)\s*\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*(['\"`])([^'\"`]*)\2",
    re.I)
_NEST_CLASS = re.compile(r"@Controller\(\s*(?:(['\"`])([^'\"`]*)\1)?\s*\)\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+\w+[^{]*\{")
_NEST_VERB = re.compile(r"@(Get|Post|Put|Delete|Patch|Head|Options)\(\s*(?:(['\"`])([^'\"`]*)\2)?\s*\)")


def _express_routes(repo_root):
    routes = []
    for rel, text in _files(repo_root, {".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx"}):
        for m in _EXPRESS.finditer(text):
            path = m.group(3)
            if path.startswith("/") or path == "":
                routes.append({"method": m.group(1).upper(), "path": path or "/", "file": rel,
                               "line": line_of(text, m.start()), "auth": None, "requestType": None,
                               "responseType": None})
        for cm in _NEST_CLASS.finditer(text):
            open_i = cm.end() - 1
            close_i = match_brace(text, open_i)
            if close_i < 0:
                continue
            prefix = cm.group(2) or ""
            class_guard = _NEST_AUTH.search(text[max(0, cm.start() - 200):cm.start()])
            body = text[open_i:close_i]
            for vm in _NEST_VERB.finditer(body):
                guard = _NEST_AUTH.search(body[max(0, vm.start() - 160):vm.start()]) or \
                    _NEST_AUTH.search(body[vm.end():vm.end() + 160].split("\n\n")[0])
                routes.append({"method": vm.group(1).upper(), "path": _join(prefix, vm.group(3)), "file": rel,
                               "line": line_of(text, open_i + vm.start()),
                               "auth": (guard or class_guard).group(1) if (guard or class_guard) else None,
                               "requestType": None, "responseType": None})
    return routes


# ---------------------------------------------------------------- public interface

def detect_framework(repo_root):
    """`aspnet`, `express` or `unknown`, from what the repository's source files use."""
    aspnet = express = 0
    for rel, full in walk(repo_root, {".cs", ".ts", ".js", ".mjs", ".cjs"}, include_tests=False):
        text = read_text(full)
        if text is None:
            continue
        if rel.endswith(".cs"):
            if re.search(r"\[ApiController\]|:\s*(?:Controller|ControllerBase)\b|\[Http(?:Get|Post|Put|Delete|Patch)\b", text):
                aspnet += 1
        elif re.search(r"from\s+['\"](?:express|@nestjs/common)['\"]|require\(\s*['\"]express['\"]\s*\)", text):
            express += 1
    if not aspnet and not express:
        return "unknown"
    return "aspnet" if aspnet >= express else "express"


def locate_routes(repo_root, framework):
    """Every route the repository defines: method, path, file (relative), line, auth, requestType, responseType."""
    if framework == "auto":
        framework = detect_framework(repo_root)
    if framework == "aspnet":
        routes = _aspnet_routes(repo_root)
    elif framework == "express":
        routes = _express_routes(repo_root)
    else:
        return []
    return sorted(routes, key=lambda r: (r["file"], r["line"], r["method"]))


def _cited(endpoint, cases):
    """True when a use case that calls the endpoint cites one of the endpoint's client files."""
    clients = {c["file"] for c in endpoint.get("clients") or [endpoint.get("client") or {}] if c.get("file")}
    for uc in endpoint.get("useCases") or []:
        files = {re.sub(r":\d+(?:-\d+)?$", "", str(f)) for f in (cases.get(uc) or {}).get("files") or []}
        if files & clients:
            return True
    return False


def _rank(endpoint_path, route, path):
    """Sort key of a matching route: lower is a closer fit. Exact normalized path, then the smallest difference in
    segment count, then the most literal segments that agree from the end of the path."""
    sa, sb = endpoint_path.strip("/").split("/"), path.strip("/").split("/")
    agree = sum(1 for x, y in zip(reversed(sa), reversed(sb)) if x == y and x != "{}")
    return (0 if path == endpoint_path else 1, abs(len(sa) - len(sb)), -agree)


def _best(endpoint, routes):
    """(route, ambiguous): the closest route that names this endpoint. When the two closest routes rank equal and sit
    in different files, route is None and ambiguous lists them."""
    hits = [(_rank(endpoint["path"], r, p), r["file"], r["line"], r) for r, p in routes
            if r["method"] == endpoint["method"] and endpoints_match(endpoint["path"], p)]
    if not hits:
        return None, []
    hits.sort(key=lambda h: h[:3])
    tied = [h for h in hits if h[0] == hits[0][0]]
    if len({h[1] for h in tied}) > 1:
        return None, [h[3] for h in tied]
    return hits[0][3], []


def repo_name(out_dir, repo_root):
    """The name a spec shows for the contract repository `repo_root`: its configured `name`, else its folder name."""
    real = os.path.realpath(repo_root)
    cfg = out.load(out_dir, out.CONFIG, {}) or {}
    for c in (cfg.get("contracts") if isinstance(cfg, dict) else None) or []:
        if isinstance(c, dict) and c.get("path") and c.get("name") and os.path.realpath(str(c["path"])) == real:
            return str(c["name"])
    return os.path.basename(real.rstrip(os.sep)) or real


def enrich(out_dir, repo_root, framework="auto"):
    """Fill `backend` and the labels of endpoints.json from the routes of one repository. Return the counts."""
    data = out.load(out_dir, "endpoints.json")
    if not isinstance(data, dict):
        die(f"{out_dir} has no endpoints.json (run render.py catalogs first)")
    if framework == "auto":
        framework = detect_framework(repo_root)
    routes = [(r, normalize_endpoint(r["path"])) for r in locate_routes(repo_root, framework)]
    routes = [(r, p) for r, p in routes if p]
    use_cases = out.load(out_dir, "use-cases.json", {}) or {}
    cases = {u.get("id"): u for u in use_cases.get("useCases", [])}
    have_cases = bool(cases)
    name = repo_name(out_dir, repo_root)
    matched = 0
    for e in data.get("endpoints", []):
        if not e.get("backend"):
            route, ambiguous = _best(e, routes)
            if route:
                e["backend"] = {"repo": name, "file": route["file"], "line": route["line"], "auth": route["auth"]}
            elif ambiguous:
                note = {"field": "route", "client": (e.get("client") or {}).get("file"),
                        "backend": " | ".join(f"{r['file']}:{r['line']}" for r in ambiguous),
                        "note": "ambiguous backend route"}
                if note not in e.setdefault("disagreements", []):
                    e["disagreements"].append(note)
        if e.get("backend") and e.get("disagreements"):
            e["disagreements"] = [d for d in e["disagreements"] if d.get("note") != "ambiguous backend route"]
            if not e["disagreements"]:
                del e["disagreements"]
        cited = _cited(e, cases) if have_cases else e.get("label") == "VERIFIED"
        if e.get("backend"):
            matched += 1
            e["label"] = "VERIFIED" if cited else "INFERRED"
        elif e.get("label") == "VERIFIED":
            e["label"] = "INFERRED"
    out.save(out_dir, "endpoints.json", data)
    return {"framework": framework, "routes": len(routes), "endpoints": len(data.get("endpoints", [])),
            "matched": matched}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out")
    ap.add_argument("--repo", action="append", metavar="PATH", help="backend repository (default: the contracts of app-spec.json)")
    ap.add_argument("--framework", default="auto", choices=("auto", "aspnet", "express"))
    args = ap.parse_args(argv)
    repos = args.repo or [c.get("path") for c in out.load_config(args.out).get("contracts", []) if c.get("path")]
    if not repos:
        print("no contract repository given; endpoints.json is unchanged")
        return 0
    for repo in repos:
        if not os.path.isdir(repo):
            die(f"{repo} is not a directory")
        result = enrich(args.out, repo, args.framework)
        print(f"{repo}: " + ", ".join(f"{k} {v}" for k, v in result.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
