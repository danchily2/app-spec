"""React Native inventory: navigator routes and their screen files, endpoints (RTK Query, axios, fetch, Apollo),
analytics catalogs, storage keys, i18n catalogs, deep-link config, remote-config flags, the native ios/ and android/
shells, dependencies (native modules flagged) and tests. Every count is returned with the rule that produced it.
"""

import json
import os
import re

from . import android as droid
from . import ios as apple
from . import notify
from . import strings as strcat
from .common import (is_test_path, line_of, looks_like_path, match_brace, normalize_endpoint, read_text,
                     sanitize_url, strip_comments, walk)

JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
_STR = r"(?:'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`)"
_CONST = re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::\s*string\s*)?=\s*(" + _STR + r")\s*(?:as\s+const\s*)?;?")
_SCREEN_TAG = re.compile(r"<\s*([A-Za-z_$][A-Za-z0-9_$]*)\.Screen\b")
_ATTR_NAME = re.compile(r"\bname\s*=\s*(?:\{\s*([^}]+?)\s*\}|(" + _STR + r"))")
_ATTR_COMP = re.compile(r"\b(?:component|getComponent)\s*=\s*\{\s*([^}]+?)\s*\}")
_IMPORT_DEFAULT = re.compile(r"import\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:,\s*\{[^}]*\})?\s*from\s*(" + _STR + r")")
_IMPORT_NAMED = re.compile(r"import\s+(?:[A-Za-z_$][A-Za-z0-9_$]*\s*,\s*)?\{([^}]*)\}\s*from\s*(" + _STR + r")")
_LAZY = re.compile(r"(?:const|let)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:React\.)?lazy\s*\(\s*\(\s*\)\s*=>\s*import\s*\(\s*(" + _STR + r")")
_URL_PROP = re.compile(r"\burl\s*:\s*(" + _STR + r")")
_QUERY_STR = re.compile(r"\bquery\s*:\s*\([^)]*\)\s*=>\s*(" + _STR + r")")
_HTTP_CALL = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\.\s*(get|post|put|patch|delete|head)\s*(?:<[^>()]*(?:<[^>]*>[^>()]*)*>)?\s*\(\s*(" + _STR + r")")
_FETCH = re.compile(r"\bfetch\s*\(\s*(" + _STR + r")")
_URL_VAR = re.compile(r"\b(?:const|let|var)\s+(?:url|uri|path|endpoint|resource|route|requestUrl|fullUrl)[A-Za-z0-9_]*\s*(?::\s*string\s*)?=\s*(" + _STR + r")")
_METHOD_ASSIGN = re.compile(r"\bmethod\s*(?::\s*[A-Za-z_.<>|'\" ]+)?\s*[:=]\s*['\"](GET|POST|PUT|PATCH|DELETE|HEAD)['\"]", re.I)
_OPEN_URL = re.compile(r"\b(?:Linking\.openURL|InAppBrowser\.open(?:Auth)?|openBrowserAsync|openUrl|openURL)\s*\(\s*(" + _STR + r")")
_GQL = re.compile(r"\b(?:gql|graphql)\s*`\s*(query|mutation|subscription|fragment)\s+([A-Za-z_][A-Za-z0-9_]*)")
_EVENTS_OBJ = re.compile(r"\b(?:export\s+)?const\s+([A-Z][A-Z0-9_]*_EVENTS)\s*(?::[^=]+)?=\s*\{")
_LOG_EVENT = re.compile(r"\b(?:logEvent|trackEvent|logScreenView)\s*\(\s*(" + _STR + r")")
_ASYNC = re.compile(r"\b(AsyncStorage|[A-Za-z_$][A-Za-z0-9_$]*[sS]torage|mmkv|MMKV|kv)\s*\.\s*(?:setItem|getItem|removeItem|mergeItem|multiGet|set|getString|getNumber|getBoolean|getBuffer|delete|remove|contains)\s*\(\s*(" + _STR + r"|[A-Z][A-Z0-9_]*\b)")
_KEYCHAIN = re.compile(r"\b(setGenericPassword|getGenericPassword|resetGenericPassword|setInternetCredentials|getInternetCredentials|setItemAsync|getItemAsync)\b")
_PERSIST = re.compile(r"\bkey\s*:\s*(" + _STR + r")\s*,[^}]{0,400}?\bstorage\s*:")
_REMOTE_CONFIG = re.compile(r"\b(?:getValue|getBoolean|getString|getNumber|getAll)\s*\(\s*(?:[A-Za-z_$][A-Za-z0-9_$]*(?:\(\s*\))?\s*,\s*)?(" + _STR + r"|[A-Z][A-Z0-9_]*(?:\.[A-Z][A-Z0-9_]*)?\b)")
_WHITELIST = re.compile(r"\bwhitelist\s*(?::\s*[^=\n]+)?[:=]\s*\[([^\]]*)\]")
_NON_API_HOST = re.compile(r"^(?:[a-z0-9-]+\.)*(github\.com|githubusercontent\.com|gitlab\.com|bitbucket\.org|npmjs\.com|npmjs\.org|apps\.apple\.com|itunes\.apple\.com|play\.google\.com|opensource\.org|creativecommons\.org|gnu\.org|apache\.org|mozilla\.org|wikipedia\.org|youtube\.com|twitter\.com|x\.com|facebook\.com|linkedin\.com|instagram\.com|developer\.apple\.com|developer\.android\.com|reactnative\.dev|example\.com|example\.org|someurl\.com)$", re.I)
_PREFIXES = re.compile(r"\bprefixes\s*:\s*\[([^\]]*)\]")
_METHOD_NEAR = re.compile(r"\bmethod\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE|HEAD)['\"]", re.I)
_TEMPLATE_EXPR = re.compile(r"\$\{\s*([A-Za-z_$][A-Za-z0-9_$.]*)\s*\}")
_HTTP_OBJECTS = {"axios", "api", "http", "client", "instance", "request", "apiClient", "httpClient", "service", "$http"}


def _lit(s):
    return s[1:-1] if s and s[0] in "'\"`" else s


def _resolve_template(raw, consts):
    def sub(m):
        name = m.group(1).split(".")[-1]
        vals = consts.get(name)
        if vals and len(vals) == 1:
            return next(iter(vals))
        return "${}"
    return _TEMPLATE_EXPR.sub(sub, raw)


def _tag_span(text, start):
    """End index of a JSX tag starting at `start` ('<'), skipping braces and strings. -1 if not found."""
    i, n, depth, in_str = start + 1, len(text), 0, None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"`":
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return i
        i += 1
    return -1


def _resolve_module(from_rel, spec, root, aliases):
    if spec.startswith((".", "/")):
        base = os.path.normpath(os.path.join(os.path.dirname(from_rel), spec))
    else:
        base = None
        for prefix, target in aliases.items():
            if spec == prefix or spec.startswith(prefix.rstrip("*").rstrip("/") + "/"):
                rest = spec[len(prefix.rstrip("*").rstrip("/")):].lstrip("/")
                base = os.path.normpath(os.path.join(target.rstrip("*").rstrip("/"), rest))
                break
        if base is None:
            return None
    for cand in [base + ext for ext in (".tsx", ".ts", ".jsx", ".js")] + [os.path.join(base, "index" + ext) for ext in (".tsx", ".ts", ".jsx", ".js")]:
        if os.path.isfile(os.path.join(root, cand)):
            return cand.replace(os.sep, "/")
    return None


def _aliases(root):
    """tsconfig/babel path aliases: {'@components/*': 'src/components/*'}."""
    out = {}
    text = read_text(os.path.join(root, "tsconfig.json")) or ""
    try:
        cfg = json.loads(re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)) if text else {}
    except ValueError:
        cfg = {}
    opts = (cfg or {}).get("compilerOptions") or {}
    base_url = opts.get("baseUrl") or "."
    for key, targets in (opts.get("paths") or {}).items():
        if targets:
            out[key] = os.path.normpath(os.path.join(base_url, targets[0])).replace(os.sep, "/")
    babel = read_text(os.path.join(root, "babel.config.js")) or ""
    alias_block = re.search(r"alias\s*:\s*\{([^}]*)\}", babel)
    if alias_block:
        for m in re.finditer(r"['\"]?([@A-Za-z0-9_~/-]+)['\"]?\s*:\s*['\"]\.?/?([^'\"]+)['\"]", alias_block.group(1)):
            out.setdefault(m.group(1), m.group(2))
    return out


def _package_json(root):
    try:
        return json.loads(read_text(os.path.join(root, "package.json")) or "{}")
    except ValueError:
        return {}


def extract(root):
    root = os.path.realpath(root)
    pkg = _package_json(root)
    aliases = _aliases(root)
    texts = {}
    consts = {}
    for rel, full in walk(root, JS_EXT):
        if rel.startswith(("ios/", "android/")) or "/node_modules/" in f"/{rel}":
            continue
        text = read_text(full)
        if text is None:
            continue
        clean = strip_comments(text)
        texts[rel] = clean
        for m in _CONST.finditer(clean):
            val = _lit(m.group(2))
            if "${" not in val:
                consts.setdefault(m.group(1), set()).add(val)

    routes, screens_by_file, unresolved, dynamic_sites = [], {}, [], []
    endpoints, graphql, events, storage, flags, prefixes, web_links = [], [], [], [], [], [], []
    test_files = 0
    for rel, text in texts.items():
        if is_test_path(rel):
            test_files += 1
            continue
        imports = {}
        for m in _IMPORT_DEFAULT.finditer(text):
            imports[m.group(1)] = _lit(m.group(2))
        for m in _IMPORT_NAMED.finditer(text):
            for part in m.group(1).split(","):
                part = part.strip()
                if not part:
                    continue
                local = part.split(" as ")[-1].strip()
                imports[local] = _lit(m.group(2))
        for m in _LAZY.finditer(text):
            imports[m.group(1)] = _lit(m.group(2))

        for m in _SCREEN_TAG.finditer(text):
            end = _tag_span(text, m.start())
            tag = text[m.start(): end + 1 if end > 0 else m.start() + 600]
            nm = _ATTR_NAME.search(tag)
            if not nm:
                continue
            if nm.group(1):
                const = nm.group(1).strip()
                last = const.split(".")[-1]
                if not re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*$", const) or not re.match(r"^[A-Z]", last):
                    dynamic_sites.append(f"{rel}:{line_of(text, m.start())}")
                    continue
                vals = consts.get(last)
                value = next(iter(vals)) if vals and len(vals) == 1 else None
            else:
                const, value = None, _lit(nm.group(2))
            comp = _ATTR_COMP.search(tag)
            comp_name = comp.group(1).strip() if comp else None
            comp_file = None
            if comp_name:
                ident = re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", comp_name)
                ident = [i for i in ident if i not in ("require", "default", "props", "React", "lazy", "import")]
                head = ident[-1] if comp_name.startswith("(") and ident else (ident[0] if ident else None)
                spec = imports.get(head) if head else None
                if spec:
                    comp_file = _resolve_module(rel, spec, root, aliases)
                if head:
                    comp_name = head
            route = {"name": const or value, "value": value, "component": comp_name, "componentFile": comp_file,
                     "navigator": m.group(1), "file": f"{rel}:{line_of(text, m.start())}"}
            routes.append(route)
            if comp_file:
                screens_by_file.setdefault(comp_file, {"name": comp_name, "file": comp_file,
                                                       "area": _area(comp_file), "kind": "rn-screen", "routes": []})
                screens_by_file[comp_file]["routes"].append(route["name"])
            elif comp_name:
                unresolved.append(route)

        for m in _PREFIXES.finditer(text):
            for lit in re.findall(_STR, m.group(1)):
                val = _lit(lit)
                if val not in prefixes:
                    prefixes.append(val)

        def add_endpoint(raw, method, client, index):
            resolved = _resolve_template(raw, consts)
            if not looks_like_path(resolved):
                return
            host = None
            hm = re.match(r"^[a-z][a-z0-9+.-]*://([^/:?#]+)", resolved, re.I)
            if hm:
                host = hm.group(1).lower()
                if _NON_API_HOST.match(host):
                    return
            if re.search(r"/(blob|tree|raw)/|licen[cs]e(\.[a-z]+)?$", resolved, re.I):
                return
            path = normalize_endpoint(resolved)
            if path:
                endpoints.append({"method": method, "path": path, "raw": raw[:200], "client": client, "host": host,
                                  "file": f"{rel}:{line_of(text, index)}"})

        is_rtk = "createApi" in text or "injectEndpoints" in text or "builder.query" in text or "builder.mutation" in text
        for m in _URL_PROP.finditer(text):
            window = _enclosing_object(text, m.start())
            mm = _METHOD_NEAR.search(window)
            method = mm.group(1).upper() if mm else ("GET" if is_rtk else None)
            add_endpoint(_lit(m.group(1)), method, "rtk-query" if is_rtk else "other", m.start())
        for m in _QUERY_STR.finditer(text):
            add_endpoint(_lit(m.group(1)), "GET", "rtk-query", m.start())
        for m in _HTTP_CALL.finditer(text):
            obj = m.group(1)
            if obj in ("searchParams", "headers", "params", "map", "cache", "Map", "store", "state", "formData", "router", "app"):
                continue
            if obj not in _HTTP_OBJECTS and not re.search(r"(api|http|client|axios|service|request)$", obj, re.I):
                continue
            add_endpoint(_lit(m.group(3)), m.group(2).upper(), "axios", m.start())
        for m in _FETCH.finditer(text):
            add_endpoint(_lit(m.group(1)), None, "fetch", m.start())
        # `const url = `${base}autopay/list``, then makeRequest({ method, url }): the method is the nearest method
        # assignment between this url assignment and its neighbours, so one request's method never leaks into another's
        url_vars = list(_URL_VAR.finditer(text))
        for k, m in enumerate(url_vars):
            lo = url_vars[k - 1].end() if k else max(0, m.start() - 800)
            hi = url_vars[k + 1].start() if k + 1 < len(url_vars) else min(len(text), m.end() + 800)
            before = list(_METHOD_ASSIGN.finditer(text, lo, m.start()))
            after = _METHOD_ASSIGN.search(text, m.end(), hi)
            # the nearest assignment wins: code that declares the method after the url (and code that declares it
            # before) both resolve to their own request, not the neighbouring function's
            cands = ([(m.start() - before[-1].end(), before[-1].group(1))] if before else []) + \
                    ([(after.start() - m.end(), after.group(1))] if after else [])
            method = min(cands)[1] if cands else None
            add_endpoint(_lit(m.group(1)), method.upper() if method else None, "http-helper", m.start())
        for m in _OPEN_URL.finditer(text):
            val = _resolve_template(_lit(m.group(1)), consts)
            if re.match(r"^https?://", val, re.I):
                web_links.append({"url": sanitize_url(val)[:300], "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _GQL.finditer(text):
            graphql.append({"kind": m.group(1), "name": m.group(2), "file": f"{rel}:{line_of(text, m.start())}"})

        for m in _EVENTS_OBJ.finditer(text):
            close = match_brace(text, m.end() - 1)
            body = text[m.end(): close] if close > 0 else ""
            depth = 0
            i = 0
            for em in re.finditer(r"([{}])|\b([A-Z][A-Z0-9_]*)\s*:\s*(" + _STR + r")", body):
                if em.group(1) == "{":
                    depth += 1
                elif em.group(1) == "}":
                    depth -= 1
                elif depth == 0:
                    events.append({"name": _lit(em.group(3)), "key": em.group(2), "family": m.group(1),
                                   "file": f"{rel}:{line_of(text, m.end() + em.start())}"})
        for m in _LOG_EVENT.finditer(text):
            val = _lit(m.group(1))
            if "${" not in val:
                events.append({"name": val, "family": "call", "file": f"{rel}:{line_of(text, m.start())}"})

        for m in _ASYNC.finditer(text):
            obj, key = m.group(1), m.group(2)
            if obj != "AsyncStorage" and not re.search(r"react-native-mmkv|MMKV|AsyncStorage|[sS]torage\s*=", text):
                continue
            resolved = True
            if key[0] in "'\"`":
                key = _lit(key)
            else:
                vals = consts.get(key)
                if vals and len(vals) == 1:
                    key = next(iter(vals))
                else:
                    resolved = False
            storage.append({"kind": "asyncstorage" if obj == "AsyncStorage" else "mmkv",
                            "key": key, "resolved": resolved, "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _PERSIST.finditer(text):
            storage.append({"kind": "redux-persist", "key": _lit(m.group(1)), "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _WHITELIST.finditer(text):
            for lit in re.findall(_STR, m.group(1)):
                storage.append({"kind": "redux-persist-slice", "key": _lit(lit), "file": f"{rel}:{line_of(text, m.start())}"})
        km = _KEYCHAIN.search(text)
        if km:
            storage.append({"kind": "keychain", "key": km.group(1), "file": f"{rel}:{line_of(text, km.start())}"})
        if "remoteConfig" in text or "remote-config" in text or "RemoteConfig" in text:
            for m in _REMOTE_CONFIG.finditer(text):
                raw_key = m.group(1)
                if raw_key[0] in "'\"`":
                    val = _lit(raw_key)
                else:
                    vals = consts.get(raw_key.split(".")[-1])
                    val = next(iter(vals)) if vals and len(vals) == 1 else raw_key
                if re.match(r"^[A-Za-z0-9_.-]{2,80}$", val) and not any(f["key"] == val for f in flags):
                    flags.append({"kind": "remote-config", "key": val, "file": f"{rel}:{line_of(text, m.start())}"})

    for rel, full in walk(root, {".graphql", ".gql"}):
        for m in re.finditer(r"\b(query|mutation|subscription|fragment)\s+([A-Za-z_][A-Za-z0-9_]*)", read_text(full) or ""):
            graphql.append({"kind": m.group(1), "name": m.group(2), "file": rel})

    catalog = strcat.find_i18n_json(root, include=["src", "app", "assets", "locales", "translations", "i18n", "lang", "res"]) \
        or strcat.combine()

    deps = []
    for section in ("dependencies", "devDependencies"):
        for name, version in sorted((pkg.get(section) or {}).items()):
            native = bool(re.match(r"^(react-native-|@react-native-|@react-native/|@react-native-community/|@react-native-firebase/|expo-|@notifee/|@sentry/react-native|@invertase/)", name))
            deps.append({"name": name, "version": version, "source": "package.json", "dev": section == "devDependencies",
                         "native": native})
    dev_deps = {d["name"] for d in deps if d["dev"]}
    frameworks = [fw for fw, key in (("Jest", "jest"), ("React Native Testing Library", "@testing-library/react-native"),
                                     ("Detox", "detox"), ("Appium", "appium"), ("Playwright", "@playwright/test"))
                  if key in dev_deps or key in (pkg.get("dependencies") or {})]

    maestro = [rel for rel, full in walk(root, {".yaml", ".yml"})
               if "maestro" in rel.lower() and re.search(r"(?m)^appId\s*:", read_text(full) or "")]
    if maestro and "Maestro" not in frameworks:
        frameworks.append("Maestro")

    ios_plat = apple.platform(os.path.join(root, "ios"), "ios/")
    and_plat = droid.platform(os.path.join(root, "android"), "android/")
    plat = _merge_platforms(ios_plat, and_plat)
    # each shell's own facts, so continuity is checked per platform (an iOS entitlement never covers Android users)
    plat["byPlatform"] = {name: {k: v for k, v in part.items() if k in PER_PLATFORM}
                          for name, part in (("ios", ios_plat), ("android", and_plat)) if os.path.isdir(os.path.join(root, name))}
    for p in prefixes:
        if "://" in p:
            scheme, _, rest = p.partition("://")
            host = rest.split("/")[0]
            if scheme in ("http", "https") and host and host not in plat["associatedDomains"]:
                plat["associatedDomains"].append(host)
            elif scheme not in ("http", "https") and scheme not in plat["urlSchemes"]:
                plat["urlSchemes"].append(scheme)
    if any(d["name"] in ("@react-native-firebase/messaging", "@notifee/react-native", "react-native-push-notification",
                         "@react-native-community/push-notification-ios", "expo-notifications") for d in deps):
        plat["push"] = True
    plat["linkingPrefixes"] = prefixes
    plat["notificationCategories"] = notify.scan(root)
    plat["flags"] = flags

    for entry in screens_by_file.values():
        body = texts.get(entry["file"], "")
        if _SCREEN_TAG.search(body) or re.search(r"\bcreate[A-Za-z]*Navigator\s*\(", body):
            entry["kind"] = "rn-navigator"
    navigators = sorted((e for e in screens_by_file.values() if e["kind"] == "rn-navigator"), key=lambda s: s["file"])
    screens = sorted((e for e in screens_by_file.values() if e["kind"] == "rn-screen"), key=lambda s: s["file"])
    catalog_events = [e for e in events if e["family"] != "call"]
    catalog_names = {e["name"] for e in catalog_events}
    call_only = {e["name"] for e in events if e["family"] == "call" and e["name"] not in catalog_names}
    screen_dirs = sorted({rel for rel in texts if re.match(r"^(src/)?screens/", rel) and not is_test_path(rel)
                          and rel.endswith((".tsx", ".jsx"))})
    distinct_routes = sorted({r["name"] for r in routes if r["name"]})
    counts = {
        "sourceFiles": sum(1 for rel in texts if not is_test_path(rel)),
        "routes": len(distinct_routes),
        "routeSites": len(routes),
        "screens": len(screens),
        "screenDirFiles": len(screen_dirs),
        "endpoints": len({e["path"] for e in endpoints}),
        "graphqlOperations": len({(g["kind"], g["name"]) for g in graphql if g["kind"] != "fragment"}),
        "events": len(catalog_names) if catalog_names else len(call_only),
        "eventCatalogMembers": len(catalog_events),
        "eventCallsOutsideCatalog": len(call_only) if catalog_names else 0,
        "navigators": len(navigators),
        "dynamicRouteSites": len(dynamic_sites),
        "stringKeys": len(catalog["keys"]),
        "locales": len(catalog["locales"]),
        "storageKeys": len(storage),
        "webLinks": len({w["url"] for w in web_links}),
        "flags": len(flags),
        "testFiles": test_files,
        "maestroFlows": len(maestro),
        "packages": sum(1 for d in deps if d["native"] and not d["dev"]),
        "dependencies": sum(1 for d in deps if not d["dev"]),
        "targets": len(ios_plat["targets"]) + len(and_plat["manifests"]),
    }
    rules = {
        "sourceFiles": "non-test .ts/.tsx/.js/.jsx files outside ios/, android/ and generated or vendored directories",
        "routes": "distinct route names (the constant when the name is a constant, else the literal) registered in a <X.Screen name=...> element",
        "routeSites": "every <X.Screen name=...> element (one route can be registered in several navigators)",
        "screens": "distinct component files registered as a route's component (resolved through the file's imports, tsconfig paths and babel aliases), navigators excluded",
        "screenDirFiles": ".tsx/.jsx files under screens/ or src/screens/ (a cross-check, not a screen count)",
        "endpoints": "distinct normalized paths from url: properties, RTK Query query: string returns, axios-style <client>.get/post/put/patch/delete calls, fetch() literals and url/path/endpoint variable assignments, in non-test, non-mock files; ${CONSTANT} templates resolved",
        "graphqlOperations": "distinct named queries, mutations and subscriptions in gql`` tags and .graphql files",
        "events": "distinct wire values of top-level members of *_EVENTS objects (when no catalog exists: distinct literals passed to logEvent/trackEvent/logScreenView)",
        "eventCatalogMembers": "top-level members of *_EVENTS objects (two members may share a wire value)",
        "eventCallsOutsideCatalog": "distinct literals passed to logEvent/trackEvent/logScreenView that are not a catalog wire value",
        "navigators": "route components whose file itself registers routes or creates a navigator (nested stacks and tabs)",
        "dynamicRouteSites": "<X.Screen> elements whose name is an expression (route.name, a map over a list), not counted as routes",
        "stringKeys": "keys (nested keys flattened with '.') in i18n JSON catalogs, union of locales",
        "locales": "locale files or folders in the i18n catalog",
        "storageKeys": "AsyncStorage/MMKV keys (literals, or constants resolved to their literal), redux-persist keys and whitelisted slices, one row per file using keychain or secure-store APIs",
        "webLinks": "absolute http(s) URLs passed to Linking.openURL, InAppBrowser.open or openBrowserAsync (help, legal and marketing pages)",
        "flags": "distinct remote-config keys read with getValue/getBoolean/getString/getNumber in files that mention remoteConfig",
        "testFiles": "files on test paths (__tests__, *.test.*, *.spec.*, mocks, msw handlers)",
        "maestroFlows": "YAML files under a maestro folder with an appId: header",
        "packages": "runtime dependencies that are React Native native modules (react-native-*, @react-native-*, @react-native-firebase/*, expo-*, ...)",
        "dependencies": "runtime dependencies in package.json",
        "targets": "native targets in ios/*.xcodeproj plus AndroidManifest.xml files under android/*/src/main",
    }
    notes = [
        "Routes registered with the static navigation API (createXNavigator({screens: {...}})) or built dynamically are not counted.",
        "Endpoint paths are relative to whichever base URL the client adds; the parity check matches them by path suffix.",
    ]
    if unresolved:
        notes.append(f"{len(unresolved)} route(s) name a component that could not be resolved to a file (inline render or re-export).")
    return {
        "stack": "react-native", "counts": counts, "rules": rules, "screens": screens, "routes": routes,
        "unresolvedRoutes": unresolved[:200], "endpoints": endpoints, "webLinks": web_links, "graphql": graphql, "events": events,
        "navigators": navigators, "storage": storage, "platform": plat, "dependencies": deps, "localPackages": [],
        "tests": {"frameworks": frameworks, "unitTestFiles": test_files, "uiTestFiles": 0, "maestroFlows": len(maestro),
                  "maestro": maestro},
        "strings": catalog, "notes": notes,
    }


def _enclosing_object(text, index):
    """The object literal around a `url:` property, so a neighbouring endpoint's `method:` is never read."""
    depth, i = 0, index
    while i > 0:
        i -= 1
        c = text[i]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                close = match_brace(text, i)
                return text[i: close + 1 if close > 0 else index + 400]
            depth -= 1
    return text[max(0, index - 200): index + 200]


def _area(rel):
    parts = rel.split("/")
    if "screens" in parts:
        i = parts.index("screens")
        return parts[i + 1] if i + 1 < len(parts) - 1 else parts[i]
    return parts[1] if len(parts) > 2 and parts[0] == "src" else parts[0]


PER_PLATFORM = {"bundleIds", "urlSchemes", "associatedDomains", "appLinkHosts", "push", "extensions", "appGroups",
                "keychainGroups", "privacyManifest", "minOS"}


def _merge_platforms(a, b):
    out = {}
    for key in set(a) | set(b):
        va, vb = a.get(key), b.get(key)
        if isinstance(va, list) or isinstance(vb, list):
            merged = list(va or [])
            for item in vb or []:
                if item not in merged:
                    merged.append(item)
            out[key] = merged
        elif isinstance(va, dict) or isinstance(vb, dict):
            out[key] = {**(va or {}), **(vb or {})}
        else:
            out[key] = bool(va) or bool(vb)
    return out
