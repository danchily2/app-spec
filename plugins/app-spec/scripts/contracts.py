#!/usr/bin/env python3
"""Find the backend route of each endpoint of the module and record it.

    python3 contracts.py <out> [--repo PATH ...] [--framework auto|aspnet|express]

Reads endpoints.json (written by render.py catalogs) from the output folder `<out>` and, for each endpoint, looks for
a route with the same method and path in a contract repository. A match fills `backend` (the repository's name, file,
line, authorization) and an unmatched endpoint keeps `backend` null. The name is the `name` of the matching entry in the
`contracts` list of app-spec.json, else the repository folder's name: an absolute path stays in app-spec.json only, so
the spec never shows a home folder. Without --repo, every repository in the `contracts`
list of app-spec.json is read, one after the other. A later repository never clears or replaces a match an earlier one
made, and a second run gives the same endpoints. Every run of a repository is recorded in `contractsRun`
(`[{repo, at}]`, one entry per repository name), even when no route matched, so status.py knows the step ran;
`render.py catalogs` writes endpoints.json from scratch, so the record goes with it and contracts.py runs again. Backend files are read, never executed or written. Standard library only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out  # noqa: E402
from speclib.common import (SOURCE_EXT, die, endpoints_match, line_of, match_brace, normalize_endpoint,  # noqa: E402
                            now_iso, read_text, strip_comments, walk)

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
# an attribute argument: string literals, interpolated strings and constant names joined by `+`, up to `,` or `)`
_ARG = r"((?:\$?@?\"(?:[^\"\\]|\\.)*\"|\([^()]*\)|[^,()\]\"])*)"
_ASP_VERB = re.compile(r"(?:\[|,)\s*Http(Get|Post|Put|Delete|Patch|Head|Options)\b(?:\(\s*(?:Template\s*=\s*)?" + _ARG + ")?")
_ROUTE = re.compile(r"(?:\[|,)\s*Route\(\s*" + _ARG)
_API_VERSION = re.compile(r"(?:\[|,)\s*ApiVersion\(\s*" + _ARG)
_CS_SCOPE_HEAD = re.compile(r"\b(class|struct|record|interface|namespace)\s+([\w.]+)[^{};]*$")
_CS_CONST = re.compile(r"\b(?:const\s+string|static\s+readonly\s+string)\s+(\w+)\s*=\s*([^;]+);")
_CS_TOKEN = re.compile(
    r"\s*(?:(\$@|@\$|\$|@)?\"((?:[^\"\\]|\\.|\"\")*)\"|nameof\(\s*([\w.]+)\s*\)|([A-Za-z_][\w.]*)|(\+))\s*")
_AUTHORIZE = re.compile(r"\[\s*Authorize\b(?:\(([^\]]*)\))?\s*\]")
_ASP_POLICY = re.compile(r"Policy\s*=\s*\"([^\"]*)\"")
_ASP_ROLES = re.compile(r"Roles\s*=\s*\"([^\"]*)\"")
_PRIMITIVES = {"string", "int", "long", "bool", "guid", "datetime", "decimal", "double", "float", "short", "byte",
               "cancellationtoken", "char", "object", "datetimeoffset", "dateonly", "timeonly", "uint", "ulong"}


_LOOK_BACK = 8000


def _attrs_before(text):
    """(attributes, offset): the run of attributes that ends `text` and the offset in `text` where it starts, or None.
    Looks back at most 8000 characters, enough for a base controller's long run of response types."""
    start = max(0, len(text) - _LOOK_BACK)
    m = _ATTRS_BEFORE.search(text, start)
    return (m.group(1), m.start(1)) if m else None


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


def _cs_class_paths(text):
    """[(offset, path)]: the nested class path in force from each offset on; None inside a method or other block.
    Namespaces do not count in the path."""
    changes, stack, last = [(0, ())], [], 0
    for m in re.finditer(r"[{};]", text):
        ch, i = m.group(0), m.start()
        if ch == "{":
            head = _CS_SCOPE_HEAD.search(text, last, i)
            if not head:
                stack.append(None)
            else:
                stack.append(() if head.group(1) == "namespace" else (head.group(2),))
        elif ch == "}" and stack:
            stack.pop()
        last = i + 1
        if ch != ";":
            changes.append((i + 1, None if None in stack else tuple(n for part in stack for n in part)))
    return changes


def _path_at(changes, offset):
    path = ()
    for start, value in changes:
        if start > offset:
            break
        path = value
    return path


class Constants:
    """The `const string` and `static readonly string` fields of a C# repository by nested class path, and the value
    of an attribute argument such as `RouteHelper.Payslip.Controller + "/x"` or an interpolated `{Root}/x`."""

    def __init__(self, files):
        self.exprs = {}  # (class, ..., name) -> (expression, the class path it is declared in)
        for _rel, text in files:
            changes = _cs_class_paths(text)
            for m in _CS_CONST.finditer(text):
                scope = _path_at(changes, m.start())
                if scope is not None:
                    self.exprs[scope + (m.group(1),)] = (m.group(2).strip(), scope)
        self._cache = {}

    def lookup(self, dotted, scope):
        """The key of the constant `dotted` names from inside `scope`: the innermost enclosing match first, then the
        only key that ends with the name's parts. None when it is unknown or ambiguous."""
        parts = tuple(dotted.split("."))
        for i in range(len(scope), -1, -1):
            if scope[:i] + parts in self.exprs:
                return scope[:i] + parts
        ends = [k for k in self.exprs if k[-len(parts):] == parts]
        return ends[0] if len(ends) == 1 else None

    def value(self, key, seen=()):
        """The string value of one constant, or None (unknown, circular or not a string expression)."""
        if key in self._cache:
            return self._cache[key]
        if key in seen:
            return None
        expr, scope = self.exprs[key]
        text, _ = self.evaluate(expr, scope, seen + (key,))
        self._cache[key] = text
        return text

    def _name(self, name, scope, seen):
        key = self.lookup(name, scope)
        return self.value(key, seen) if key else None

    def evaluate(self, expr, scope=(), seen=()):
        """(text, None) for an expression of literals, interpolations, nameof and constant names joined by `+`, else
        (None, the first name or expression that could not be resolved)."""
        pieces, pos, expr = [], 0, expr.strip()
        expect_value = True
        while pos < len(expr):
            m = _CS_TOKEN.match(expr, pos)
            if not m or m.end() == pos:
                return None, expr
            pos = m.end()
            prefix, literal, nameof, name, plus = m.groups()
            if plus:
                if expect_value:
                    return None, expr
                expect_value = True
                continue
            if not expect_value:
                return None, expr
            expect_value = False
            if literal is not None:
                if prefix and "$" in prefix:
                    text, missing = self._interpolate(literal, scope, seen)
                    if text is None:
                        return None, missing
                    pieces.append(text)
                else:
                    pieces.append(literal.replace('""', '"') if prefix else literal)
            elif nameof:
                pieces.append(nameof.rsplit(".", 1)[-1])
            else:
                text = self._name(name, scope, seen)
                if text is None:
                    return None, name
                pieces.append(text)
        if expect_value:
            return None, expr
        return "".join(pieces), None

    def _interpolate(self, literal, scope, seen):
        missing = []

        def repl(m):
            text = self._name(m.group(1), scope, seen)
            if text is None:
                missing.append(m.group(1))
                return ""
            return text

        text = re.sub(r"(?<!\{)\{([A-Za-z_][\w.]*)\}(?!\})", repl, literal)
        return (None, missing[0]) if missing else (text.replace("{{", "{").replace("}}", "}"), None)


def _cs_arg(constants, arg, scope):
    """(template, unresolved name) of an attribute argument. ("", None) when there is no argument."""
    if arg is None or not arg.strip():
        return "", None
    return constants.evaluate(arg, scope)


_BASE = re.compile(r"\s*(?:<[^>{]*>)?\s*(?:\([^)]*\))?\s*:\s*([\w.]+)")


def _aspnet_classes(files):
    """Every class of the repository: name -> [{file, text, match, open, close, attrs, scope, base}]."""
    classes = {}
    for rel, text in files:
        scopes = _cs_class_paths(text)
        for cm in _CLASS.finditer(text):
            open_i = text.find("{", cm.end())
            if open_i < 0:
                continue
            close_i = match_brace(text, open_i)
            if close_i < 0:
                continue
            head = _attrs_before(_MODIFIERS.sub("", text[:cm.start()]))
            base = _BASE.match(text, cm.end())
            classes.setdefault(cm.group(1), []).append({
                "file": rel, "text": text, "match": cm, "open": open_i, "close": close_i,
                "attrs": head[0] if head else "", "scope": (_path_at(scopes, cm.start()) or ()) + (cm.group(1),),
                "base": base.group(1).rsplit(".", 1)[-1] if base else None})
    return classes


def _inherited(classes, cls, pattern, seen=()):
    """(attribute argument, the class that carries it) for the first class up the base chain whose attributes match
    `pattern`, or (None, None). A base is followed only when exactly one class has its name."""
    m = pattern.search(cls["attrs"])
    if m:
        return m.group(1), cls
    base = classes.get(cls["base"] or "") or []
    if len(base) != 1 or cls["base"] in seen:
        return None, None
    return _inherited(classes, base[0], pattern, seen + (cls["base"],))


def _class_prefix(constants, classes, cls):
    """(prefix, unresolved name) of a controller: its own or an inherited `[Route]`, with `[controller]` and the
    `{version}` of `[ApiVersion]` filled in."""
    arg, owner = _inherited(classes, cls, _ROUTE)
    if owner is None:
        return "", None
    prefix, missing = _cs_arg(constants, arg, owner["scope"])
    if prefix is None:
        return None, missing
    name = cls["match"].group(1)
    prefix = prefix.replace("[controller]", name[:-len("Controller")] if name.endswith("Controller") else name)
    arg, owner = _inherited(classes, cls, _API_VERSION)
    version = _cs_arg(constants, arg, owner["scope"])[0] if owner else None
    if version:
        prefix = re.sub(r"\{version(?::[^}]*)?\}", version.split(".")[0], prefix)
    return prefix, None


def _class_auth(classes, cls, seen=()):
    """The authorization of a controller's own `[Authorize]`, else of the nearest base class that has one."""
    auth = _aspnet_auth(cls["attrs"])
    base = classes.get(cls["base"] or "") or []
    if auth or len(base) != 1 or cls["base"] in seen:
        return auth
    return _class_auth(classes, base[0], seen + (cls["base"],))


def _aspnet_routes(repo_root):
    routes = []
    files = list(_files(repo_root, {".cs"}))
    constants = Constants(files)
    classes = _aspnet_classes(files)
    for cls in (c for group in classes.values() for c in group):
        text, rel, open_i, scope = cls["text"], cls["file"], cls["open"], cls["scope"]
        prefix, prefix_missing = _class_prefix(constants, classes, cls)
        class_auth = _class_auth(classes, cls)
        body = text[open_i:cls["close"]]
        for sm in _SIGNATURE.finditer(body):
            before = _attrs_before(body[:sm.start()])
            if not before:
                continue
            attrs, attrs_at = before
            params_open = sm.end() - 1
            params_close = match_brace(body, params_open, "(", ")")
            params = body[params_open + 1:params_close] if params_close > 0 else ""
            action_route = _ROUTE.search(attrs)
            for verb in _ASP_VERB.finditer(attrs):  # an action may carry several verb attributes
                arg = verb.group(2)
                if (arg is None or not arg.strip()) and action_route:
                    arg = action_route.group(1)  # [HttpGet] [Route("x")]: the action's Route is the template
                template, missing = _cs_arg(constants, arg, scope)
                missing = prefix_missing or missing
                path = _join(prefix, template) if prefix is not None and template is not None else None
                # the line of the verb attribute: the start of the attribute block plus the lines before the verb
                verb_index = open_i + attrs_at + verb.start()
                entry = {
                    "method": verb.group(1).upper(), "path": path, "file": rel, "line": line_of(text, verb_index),
                    "auth": _aspnet_auth(attrs) or class_auth,
                    "requestType": _aspnet_request_type(params, f"{prefix or ''}/{template or ''}"),
                    "responseType": _unwrap(sm.group(1)),
                }
                if missing:
                    entry["constant"] = missing
                routes.append(entry)
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
    return sorted(routes, key=lambda r: (r["file"], r["line"], r["method"], r["path"] or ""))


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
    located = locate_routes(repo_root, framework)
    unresolved = [{k: r[k] for k in ("method", "file", "line", "constant")} for r in located if r.get("constant")]
    routes = [(r, normalize_endpoint(r["path"])) for r in located if r.get("path")]
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
    # The record that this repository was read, whether or not a route matched: status.py tests on it. A second run
    # of the same repository replaces its own entry.
    runs = [r for r in data.get("contractsRun") or [] if isinstance(r, dict) and r.get("repo") != name]
    run = {"repo": name, "at": now_iso().replace("+00:00", "Z")}
    if unresolved:  # a lead for the contract reader: the route exists, but its constant could not be resolved
        run["unresolvedRoutes"] = unresolved
    data["contractsRun"] = runs + [run]
    out.save(out_dir, "endpoints.json", data)
    result = {"framework": framework, "routes": len(routes), "endpoints": len(data.get("endpoints", [])),
              "matched": matched}
    if unresolved:
        result["unresolved"] = len(unresolved)
    return result


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
