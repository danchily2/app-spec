"""Native iOS inventory: Xcode targets, Info.plist and entitlements, screens, coordinators, API requests, analytics,
storage, string catalogs, tests and dependencies. Every count is returned with the rule that produced it.
"""

import os
import plistlib
import re

from . import notify
from . import strings as strcat
from .common import (is_test_path, line_of, looks_like_path, match_brace, normalize_endpoint, read_text,
                     sanitize_url, strip_comments, walk)

PRODUCT_KIND = {
    "com.apple.product-type.application": "app",
    "com.apple.product-type.app-extension": "extension",
    "com.apple.product-type.extensionkit-extension": "extension",
    "com.apple.product-type.watchkit2-extension": "watch-extension",
    "com.apple.product-type.application.watchapp2": "watch-app",
    "com.apple.product-type.application.watchapp2-container": "watch-app",
    "com.apple.product-type.app-clip": "app-clip",
    "com.apple.product-type.bundle.unit-test": "unit-tests",
    "com.apple.product-type.bundle.ui-testing": "ui-tests",
    "com.apple.product-type.framework": "framework",
    "com.apple.product-type.library.static": "library",
}

EXTENSION_POINTS = {
    "com.apple.share-services": "share",
    "com.apple.widgetkit-extension": "widget",
    "com.apple.usernotifications.service": "notification-service",
    "com.apple.usernotifications.content-extension": "notification-content",
    "com.apple.intents-service": "intents",
    "com.apple.intents-ui-service": "intents-ui",
    "com.apple.fileprovider-nonui": "file-provider",
    "com.apple.keyboard-service": "keyboard",
    "com.apple.ui-services": "action",
    "com.apple.services": "action",
    "com.apple.appintents-extension": "app-intents",
    "com.apple.deviceactivity.monitor-extension": "device-activity",
}

_TARGET = re.compile(r"\n\s*[0-9A-F]{24} /\* (?P<label>[^*]+?) \*/ = \{\s*isa = PBXNativeTarget;(?P<body>.*?)\n\s*\};", re.S)
_SETTING = lambda key: re.compile(r"\b" + key + r"\s*=\s*\"?([^\";\n]+)\"?;")


def _plist(path):
    try:
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    except Exception:  # plistlib raises several types for malformed files
        return None


def find_xcodeprojects(root):
    found = []
    for dirpath, dirnames, _ in os.walk(root, followlinks=False):
        keep = []
        for d in dirnames:
            if d.endswith(".xcodeproj"):
                if d != "Pods.xcodeproj":
                    found.append(os.path.join(dirpath, d))
            elif d not in {".git", "Pods", "node_modules", "build", "DerivedData", ".build", "Carthage"} and not d.endswith(
                (".xcworkspace", ".xcassets", ".lproj", ".bundle", ".framework", ".xcframework")):
                keep.append(d)
        dirnames[:] = keep
    return sorted(found)


def parse_pbxproj(xcodeproj):
    text = read_text(os.path.join(xcodeproj, "project.pbxproj"), limit=20_000_000) or ""
    targets = []
    for m in _TARGET.finditer(text):
        body = m.group("body")
        pt = re.search(r"productType\s*=\s*\"?([^\";]+)\"?;", body)
        nm = re.search(r"\bname\s*=\s*\"?([^\";]+)\"?;", body)
        ptype = pt.group(1) if pt else ""
        targets.append({"name": (nm.group(1) if nm else m.group("label")).strip(), "productType": ptype,
                        "kind": PRODUCT_KIND.get(ptype, ptype.rsplit(".", 1)[-1] or "unknown")})

    def values(key):
        return sorted({v.strip() for v in _SETTING(key).findall(text) if v.strip()})

    return {
        "project": os.path.basename(xcodeproj),
        "targets": targets,
        # test bundles (EmployeeTests, AppUITests) are not identities a store listing or a keychain group depends on
        "bundleIds": [b for b in values("PRODUCT_BUNDLE_IDENTIFIER")
                      if b and not b.startswith("$(") and not re.search(r"(?i)(ui)?tests?$", b)],
        "deploymentTargets": values("IPHONEOS_DEPLOYMENT_TARGET"),
        "infoPlists": values("INFOPLIST_FILE"),
        "entitlements": values("CODE_SIGN_ENTITLEMENTS"),
        "swiftVersions": values("SWIFT_VERSION"),
    }


def _version_key(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.]", v))


def _expand(value, settings):
    """Expand $(VAR) / ${VAR} from build settings; one value per distinct setting value (Debug and Release may differ)."""
    m = re.fullmatch(r"\$[({]([A-Z][A-Z0-9_]*)[)}]", str(value).strip())
    if not m:
        return [value]
    vals = sorted(settings.get(m.group(1)) or [])
    return vals or [value]


def platform(root, rel_prefix=""):
    """Platform facts of the iOS side of an app (a native app root, or a React Native app's ios/ folder).

    rel_prefix is prepended to every path so evidence stays relative to the app root."""
    root = os.path.realpath(root)
    out = {"bundleIds": [], "urlSchemes": [], "associatedDomains": [], "backgroundModes": [], "permissions": [],
           "extensions": [], "appGroups": [], "keychainGroups": [], "push": False, "minOS": {}, "entitlements": [],
           "queriesSchemes": [], "atsExceptions": [], "privacyManifest": [], "targets": [], "projects": []}
    if not os.path.isdir(root):
        return out
    min_targets = []
    settings = {}
    for rel, full in walk(root, {".xcconfig"}):
        for m in re.finditer(r"(?m)^\s*([A-Z][A-Z0-9_]*)\s*=\s*([^\n/]+)", read_text(full) or ""):
            settings.setdefault(m.group(1), set()).add(m.group(2).strip())
    for proj in find_xcodeprojects(root):
        text = read_text(os.path.join(proj, "project.pbxproj"), limit=20_000_000) or ""
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]*)\s*=\s*\"?([^\";\n]+)\"?;", text):
            if not m.group(1).startswith(("PRODUCT_", "CODE_SIGN", "INFOPLIST", "SWIFT_", "GCC_", "CLANG_", "OTHER_", "LD_", "HEADER_")):
                settings.setdefault(m.group(1), set()).add(m.group(2).strip())
        info = parse_pbxproj(proj)
        out["projects"].append(rel_prefix + os.path.relpath(proj, root).replace(os.sep, "/"))
        out["targets"] += info["targets"]
        out["bundleIds"] += [b for b in info["bundleIds"] if b not in out["bundleIds"]]
        min_targets += info["deploymentTargets"]
    if min_targets:
        out["minOS"]["ios"] = min(min_targets, key=_version_key)

    for rel, full in walk(root, {".plist", ".entitlements", ".xcprivacy"}):
        if "/Pods/" in f"/{rel}" or is_test_path(rel):
            continue
        name = os.path.basename(rel)
        shown = rel_prefix + rel
        if name.endswith(".xcprivacy"):
            out["privacyManifest"].append(shown)
            continue
        data = _plist(full)
        if not isinstance(data, dict):
            continue
        if name.endswith(".entitlements"):
            for key, value in data.items():
                if key not in out["entitlements"]:
                    out["entitlements"].append(key)
                if key == "aps-environment":
                    out["push"] = True
                elif key == "com.apple.developer.associated-domains":
                    out["associatedDomains"] += [d for d in value or [] if d not in out["associatedDomains"]]
                elif key == "com.apple.security.application-groups":
                    out["appGroups"] += [g for g in value or [] if g not in out["appGroups"]]
                elif key == "keychain-access-groups":
                    out["keychainGroups"] += [g for g in value or [] if g not in out["keychainGroups"]]
            continue
        if name != "Info.plist" and not name.endswith("-Info.plist"):
            continue
        for key, value in data.items():
            if key.startswith("NS") and key.endswith("UsageDescription"):
                if not any(p["key"] == key for p in out["permissions"]):
                    out["permissions"].append({"key": key, "file": shown})
        for url_type in data.get("CFBundleURLTypes") or []:
            for scheme in (url_type or {}).get("CFBundleURLSchemes") or []:
                for value in _expand(scheme, settings):
                    if value not in out["urlSchemes"]:
                        out["urlSchemes"].append(value)
        for mode in data.get("UIBackgroundModes") or []:
            if mode not in out["backgroundModes"]:
                out["backgroundModes"].append(mode)
        for scheme in data.get("LSApplicationQueriesSchemes") or []:
            if scheme not in out["queriesSchemes"]:
                out["queriesSchemes"].append(scheme)
        ats = data.get("NSAppTransportSecurity") or {}
        if isinstance(ats, dict):
            for key in ("NSAllowsArbitraryLoads", "NSAllowsArbitraryLoadsInWebContent", "NSAllowsLocalNetworking"):
                if ats.get(key):
                    out["atsExceptions"].append(f"{key} ({shown})")
            for domain in (ats.get("NSExceptionDomains") or {}):
                out["atsExceptions"].append(f"exception domain {domain} ({shown})")
        ext = data.get("NSExtension") or {}
        if isinstance(ext, dict) and ext.get("NSExtensionPointIdentifier"):
            point = ext["NSExtensionPointIdentifier"]
            out["extensions"].append({"point": point, "type": EXTENSION_POINTS.get(point, point.rsplit(".", 1)[-1]),
                                      "plist": shown})
        bid = data.get("CFBundleIdentifier")
        if isinstance(bid, str) and bid and not bid.startswith("$(") and bid not in out["bundleIds"]:
            out["bundleIds"].append(bid)
    return out


# ---------------------------------------------------------------- Swift source

_SWIFT_STRING = r'"(?:[^"\\\n]|\\.)*"'
_CONST = re.compile(r"\b(?:static\s+)?let\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*String\s*)?=\s*(" + _SWIFT_STRING + r")")
_TYPE_DECL = re.compile(r"\b(struct|class|enum|actor|extension)\s+([A-Za-z_][A-Za-z0-9_.]*)([^{;]*)\{")
_UIKIT = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]*>)?\s*:\s*([A-Za-z_][A-Za-z0-9_.]*)")
_OBJC_UIKIT = re.compile(r"@interface\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*ViewController)\b")
_SWIFTUI = re.compile(r"\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>{]*>)?\s*:\s*(?:[A-Za-z_][A-Za-z0-9_.]*\s*,\s*)*View\b")
_REDUCER = re.compile(r"@Reducer\b(?:\s*\([^)]*\))?\s*(?:(?:public|internal|package|private|fileprivate|final)\s+)*(?:struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)")
_COORD = re.compile(r"\b(class|struct|protocol|enum|actor)\s+((?:[A-Za-z_][A-Za-z0-9_]*)?Coordinator[A-Za-z0-9_]*)")
_PATH_PROP = re.compile(r"\b(?:var|let)\s+(resourceName|path|endpoint|urlPath|route|relativePath|apiPath)\s*:\s*String\s*\{")
_PATH_LET = re.compile(r"\blet\s+(resourceName|path|endpoint|urlPath|relativePath|apiPath)\s*(?::\s*String\s*)?=\s*(" + _SWIFT_STRING + r")")
_URL_CALL = re.compile(r"\b(?:URL\s*\(\s*string\s*:|appendingPathComponent\s*\(|AF\.request\s*\(|\.request\s*\()\s*(" + _SWIFT_STRING + r")")
_METHOD_PROP = re.compile(r"\b(?:var|let)\s+(?:method|httpMethod|requestMethod)\s*(?::\s*[A-Za-z_.]+\s*)?(=|\{)")
_METHOD_WORD = re.compile(r"\b(GET|POST|PUT|DELETE|PATCH|HEAD)\b|\.(get|post|put|delete|patch|head)\b|\"(GET|POST|PUT|DELETE|PATCH|HEAD)\"", re.I)
_INTERP = re.compile(r"\\\(([^()]*(?:\([^()]*\)[^()]*)*)\)")
_EVENT_ENUM = re.compile(r"\benum\s+((?:[A-Za-z_][A-Za-z0-9_]*)?(?:Event|Events|Analytics|AnalyticsEvent|TrackingEvent))\b[^{]*\{")
_CASE = re.compile(r"(?m)^\s*case\s+([^\n]+)")
_LOG_EVENT = re.compile(r"\b(?:logEvent|trackEvent|track)\s*\(\s*(?:name\s*:\s*)?(" + _SWIFT_STRING + r")")
_DEFAULTS = re.compile(r"(?:UserDefaults[A-Za-z0-9_.()]*|[dD]efaults)\s*\.\s*(?:set|string|bool|integer|double|float|data|object|array|dictionary|url|removeObject|stringArray)\s*\([^)\n]*?forKey\s*:\s*(" + _SWIFT_STRING + r")")
_APPSTORAGE = re.compile(r"@AppStorage\s*\(\s*(" + _SWIFT_STRING + r")")
_REALM = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:RealmSwift\.)?(?:Object|EmbeddedObject)\b")
_SWIFTDATA = re.compile(r"@Model\s+(?:(?:public|final|internal)\s+)*class\s+([A-Za-z_][A-Za-z0-9_]*)")
_KEYCHAIN = re.compile(r"\b(Keychain[A-Za-z0-9_]*|SecItemAdd|SecItemCopyMatching|kSecClassGenericPassword)\b")


def _literal(s):
    return s[1:-1] if s and s[0] == '"' else s


def _resolve(literal, consts):
    """Replace \\(A.B.name) interpolations by the constant 'name' when it has exactly one literal value.

    Only qualified names (with a dot) are resolved: a bare \\(userId) is a parameter, even when some unrelated
    constant happens to share its name."""
    def sub(m):
        expr = m.group(1).strip()
        if "." not in expr or "(" in expr:
            return "{}"
        last = expr.split(".")[-1].strip()
        vals = consts.get(last)
        if vals and len(vals) == 1:
            return next(iter(vals))
        return "{}"
    prev = None
    out = literal
    for _ in range(3):  # constants may themselves contain interpolations
        prev, out = out, _INTERP.sub(sub, out)
        if out == prev:
            break
    return out


def _type_spans(text):
    spans = []
    for m in _TYPE_DECL.finditer(text):
        open_i = m.end() - 1
        close_i = match_brace(text, open_i)
        if close_i > 0:
            spans.append((m.start(), close_i, m.group(1), m.group(2), m.group(3)))
    return spans


def _enclosing(spans, index):
    best = None
    for s in spans:
        if s[0] <= index <= s[1] and s[2] != "extension" and (best is None or s[0] >= best[0]):
            best = s
    return best


def _method_in(body):
    """HTTP method declared by a method/httpMethod property inside a type or extension body, else None."""
    for m in _METHOD_PROP.finditer(body):
        if m.group(1) == "{":
            close = match_brace(body, m.end() - 1)
            expr = body[m.end(): close if close > 0 else m.end() + 200]
        else:
            expr = body[m.end(): m.end() + 120].split("\n")[0]
        w = _METHOD_WORD.search(expr)
        if w:
            return (w.group(1) or w.group(2) or w.group(3)).upper()
    return None


def _protocol_defaults(texts):
    """Default HTTP method a protocol extension gives its conformers: {'APIClientRequest': 'GET'}."""
    defaults = {}
    for rel, text in texts.items():
        if not rel.endswith(".swift") or is_test_path(rel):
            continue
        for m in re.finditer(r"\bextension\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:where[^{]*)?\{", text):
            close = match_brace(text, m.end() - 1)
            if close < 0:
                continue
            method = _method_in(text[m.end(): close])
            if method:
                defaults.setdefault(m.group(1), method)
    return defaults


def extract(root):
    """Full inventory of a native iOS app rooted at `root` (the folder with the .xcodeproj or Package.swift)."""
    root = os.path.realpath(root)
    files = [(rel, full) for rel, full in walk(root, {".swift", ".m", ".h"})]
    texts = {}
    consts = {}
    for rel, full in files:
        text = read_text(full)
        if text is None:
            continue
        clean = strip_comments(text)
        texts[rel] = clean
        if rel.endswith(".swift"):
            for m in _CONST.finditer(clean):
                consts.setdefault(m.group(1), set()).add(_literal(m.group(2)))

    method_defaults = _protocol_defaults(texts)
    screens, coordinators, endpoints, events, storage, web_links = [], [], [], [], [], []
    swiftui_views = []
    test_files, ui_test_files, frameworks = 0, 0, set()
    request_types = 0
    for rel, text in texts.items():
        if is_test_path(rel):
            if rel.endswith(".swift"):
                test_files += 1
                if "XCUIApplication" in text:
                    ui_test_files += 1
                if re.search(r"^\s*import\s+XCTest\b", text, re.M):
                    frameworks.add("XCTest")
                if re.search(r"^\s*import\s+Testing\b", text, re.M):
                    frameworks.add("Swift Testing")
                if re.search(r"^\s*import\s+SnapshotTesting\b", text, re.M):
                    frameworks.add("SnapshotTesting")
            continue
        if rel.endswith((".m", ".h")):
            for m in _OBJC_UIKIT.finditer(text):
                screens.append({"name": m.group(1), "file": f"{rel}:{line_of(text, m.start())}", "area": rel.split("/")[0],
                                "kind": "uikit-controller"})
            continue
        for m in _UIKIT.finditer(text):
            name, sup = m.group(1), m.group(2).split(".")[-1]
            if re.search(r"(ViewController|TableViewController|CollectionViewController|HostingController|PageViewController)$", sup) \
                    or (name.endswith("ViewController") and sup.endswith("Controller")):
                screens.append({"name": name, "file": f"{rel}:{line_of(text, m.start())}", "area": rel.split("/")[0],
                                "kind": "uikit-controller", "superclass": sup})
        for m in _REDUCER.finditer(text):
            screens.append({"name": m.group(1), "file": f"{rel}:{line_of(text, m.start())}", "area": rel.split("/")[0],
                            "kind": "tca-feature"})
        for m in _SWIFTUI.finditer(text):
            swiftui_views.append({"name": m.group(1), "file": f"{rel}:{line_of(text, m.start())}", "area": rel.split("/")[0],
                                  "kind": "swiftui-view"})
        for m in _COORD.finditer(text):
            coordinators.append({"name": m.group(2), "kind": m.group(1), "file": f"{rel}:{line_of(text, m.start())}"})

        spans = None
        found_here = []
        for m in _PATH_PROP.finditer(text):
            body_open = m.end() - 1
            body_close = match_brace(text, body_open)
            if body_close < 0:
                continue
            body = text[body_open:body_close]
            for lit in re.finditer(_SWIFT_STRING, body):
                found_here.append((body_open + lit.start(), _literal(lit.group(0))))
        for m in _PATH_LET.finditer(text):
            found_here.append((m.start(2), _literal(m.group(2))))
        for m in _URL_CALL.finditer(text):
            found_here.append((m.start(1), _literal(m.group(1))))
        for index, raw in found_here:
            resolved = _resolve(raw, consts)
            if not looks_like_path(resolved):
                continue
            path = normalize_endpoint(resolved)
            if not path:
                continue
            host_m = re.match(r"^https?://([^/:?#]+)", resolved, re.I)
            if host_m and not re.search(r"/api/|/v[0-9]+/|/rest/|/graphql", resolved, re.I) and not _PATH_PROP.search(text[max(0, index - 400):index]):
                web_links.append({"url": sanitize_url(resolved)[:300], "file": f"{rel}:{line_of(text, index)}"})
                continue
            if spans is None:
                spans = _type_spans(text)
            owner = _enclosing(spans, index)
            method, client, type_name = None, "urlsession", None
            if owner:
                body = text[owner[0]:owner[1]]
                method = _method_in(body)
                type_name = owner[3]
                conforms = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", owner[4] or "")
                if method is None:
                    method = next((method_defaults[c] for c in conforms if c in method_defaults), None)
                if any(c.endswith("Request") for c in conforms):
                    client = "api-client-request"
            endpoints.append({"method": method, "path": path, "raw": raw[:200], "client": client, "type": type_name,
                              "file": f"{rel}:{line_of(text, index)}"})
        if re.search(r":\s*[^{]*\bAPIClientRequest\b", text):
            request_types += len(re.findall(r"\b(?:struct|class|enum)\s+[A-Za-z_][A-Za-z0-9_]*\s*(?:<[^>]*>)?\s*:\s*[^{]*\b[A-Za-z]*Request\b[^{]*\{", text))

        for m in _EVENT_ENUM.finditer(text):
            close = match_brace(text, m.end() - 1)
            body = text[m.end():close] if close > 0 else ""
            depth_body = _top_level(body)
            for cm in _CASE.finditer(depth_body):
                for part in _split_cases(cm.group(1)):
                    nm = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*(" + _SWIFT_STRING + r"))?", part)
                    if nm:
                        events.append({"name": _literal(nm.group(2)) if nm.group(2) else nm.group(1), "family": m.group(1),
                                       "file": f"{rel}:{line_of(text, m.end() + cm.start())}"})
        for m in _LOG_EVENT.finditer(text):
            events.append({"name": _literal(m.group(1)), "family": "call", "file": f"{rel}:{line_of(text, m.start())}"})

        for m in _DEFAULTS.finditer(text):
            storage.append({"kind": "userdefaults", "key": _literal(m.group(1)), "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _APPSTORAGE.finditer(text):
            storage.append({"kind": "appstorage", "key": _literal(m.group(1)), "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _REALM.finditer(text):
            storage.append({"kind": "realm-model", "key": m.group(1), "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _SWIFTDATA.finditer(text):
            storage.append({"kind": "swiftdata-model", "key": m.group(1), "file": f"{rel}:{line_of(text, m.start())}"})
        km = _KEYCHAIN.search(text)
        if km:
            storage.append({"kind": "keychain", "key": km.group(1), "file": f"{rel}:{line_of(text, km.start())}"})

    for rel, full in walk(root, None):
        if rel.endswith(".xcdatamodeld/contents") or re.search(r"\.xcdatamodel/contents$", rel):
            for m in re.finditer(r"<entity\s+name=\"([^\"]+)\"", read_text(full) or ""):
                storage.append({"kind": "coredata-entity", "key": m.group(1), "file": rel})

    xc = [rel for rel, _ in walk(root, {".xcstrings"}) if not is_test_path(rel)]
    lproj = [rel for rel, _ in walk(root, {".strings"}) if ".lproj/" in rel and not is_test_path(rel) and "/Pods/" not in f"/{rel}"]
    catalog = strcat.combine(strcat.parse_xcstrings(root, xc), strcat.parse_lproj_strings(root, lproj))

    local_packages, remote_packages = [], []
    for rel, full in walk(root, None):
        base = os.path.basename(rel)
        if base == "Package.swift":
            m = re.search(r"Package\s*\(\s*name\s*:\s*\"([^\"]+)\"", read_text(full) or "")
            local_packages.append({"name": m.group(1) if m else os.path.basename(os.path.dirname(rel)) or "root",
                                   "file": rel})
        elif base == "Package.resolved":
            remote_packages += _package_resolved(full, rel)
        elif base == "Podfile.lock":
            remote_packages += _podfile_lock(full, rel)
    seen = set()
    deps = []
    for d in remote_packages:
        if d["name"].lower() in seen:
            continue
        seen.add(d["name"].lower())
        deps.append(d)

    maestro = _maestro_flows(root)
    plat = platform(root)
    plat["notificationCategories"] = notify.scan(root)
    uniq_endpoints = sorted({(e["method"] or "?", e["path"]) for e in endpoints})
    uniq_events = sorted({e["name"] for e in events})
    counts = {
        "sourceFiles": sum(1 for rel in texts if not is_test_path(rel)),
        "screens": len(screens),
        "uikitControllers": sum(1 for s in screens if s["kind"] == "uikit-controller"),
        "tcaFeatures": sum(1 for s in screens if s["kind"] == "tca-feature"),
        "swiftuiViews": len(swiftui_views),
        "coordinators": len(coordinators),
        "requestTypes": request_types,
        "endpoints": len({p for _, p in uniq_endpoints}),
        "events": len(uniq_events),
        "stringKeys": len(catalog["keys"]),
        "locales": len(catalog["locales"]),
        "storageKeys": len(storage),
        "webLinks": len({w["url"] for w in web_links}),
        "testFiles": test_files,
        "maestroFlows": len(maestro),
        "packages": len(local_packages),
        "dependencies": len(deps),
        "targets": len(plat["targets"]),
    }
    rules = {
        "sourceFiles": "non-test .swift, .m and .h files, generated and vendored directories excluded",
        "screens": "UIKit view controllers (a class whose superclass ends in ViewController, or ObjC @interface of one) plus TCA features (@Reducer types), outside test paths",
        "uikitControllers": "classes whose superclass name ends in ViewController, TableViewController, CollectionViewController, HostingController or PageViewController",
        "tcaFeatures": "struct or enum declarations annotated @Reducer",
        "swiftuiViews": "structs conforming to View (every View, not only screens)",
        "coordinators": "type declarations (class, struct, protocol, enum, actor) whose name contains 'Coordinator', outside test paths",
        "requestTypes": "struct/class/enum declarations conforming to a protocol ending in 'Request', in files that mention APIClientRequest",
        "endpoints": "distinct normalized paths from resourceName/path/endpoint properties, let-path literals and URL(string:)/appendingPathComponent calls; \\(constant) interpolations resolved when the constant has one literal value",
        "events": "distinct case names (or raw values) of enums whose name ends in Event, Events, Analytics, AnalyticsEvent or TrackingEvent, plus string literals passed to logEvent/trackEvent/track",
        "webLinks": "absolute http(s) URLs opened with URL(string:) outside request types whose path has no /api/, /vN/, /rest/ or /graphql segment (help, legal and marketing pages)",
        "stringKeys": "keys in .xcstrings catalogs plus keys of .strings files in *.lproj folders (union of locales)",
        "locales": "locales present in any string catalog",
        "storageKeys": "UserDefaults forKey literals, @AppStorage keys, Realm and SwiftData model classes, Core Data entities, and one row per file using Keychain APIs",
        "testFiles": ".swift files on test paths",
        "maestroFlows": "YAML files containing an appId: header and at least one Maestro command",
        "packages": "local Package.swift manifests",
        "dependencies": "distinct remote packages pinned in Package.resolved or Podfile.lock",
        "targets": "PBXNativeTarget entries in every .xcodeproj except Pods",
    }
    notes = [
        "Endpoints built at runtime (HATEOAS links, server-provided URLs, string concatenation across functions) are not visible to this scan.",
        "SwiftUI views are listed separately because most are sub-views, not screens; the map step decides which are screens.",
    ]
    return {
        "stack": "ios-native", "counts": counts, "rules": rules,
        "screens": screens, "swiftuiViews": swiftui_views, "coordinators": coordinators,
        "routes": [], "endpoints": endpoints, "webLinks": web_links, "events": events, "storage": storage,
        "platform": plat, "dependencies": deps, "localPackages": local_packages,
        "tests": {"frameworks": sorted(frameworks), "unitTestFiles": test_files - ui_test_files,
                  "uiTestFiles": ui_test_files, "maestroFlows": len(maestro), "maestro": maestro},
        "strings": catalog, "notes": notes,
    }


def _top_level(body):
    """Keep only depth-0 text of an enum body, so nested types and switch statements do not contribute cases."""
    out, depth = [], 0
    for ch in body:
        if ch == "{":
            depth += 1
            out.append(" ")
            continue
        if ch == "}":
            depth -= 1
            out.append(" ")
            continue
        out.append(ch if depth == 0 else ("\n" if ch == "\n" else " "))
    return "".join(out)


def _split_cases(text):
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


def _package_resolved(full, rel):
    import json
    try:
        data = json.loads(read_text(full) or "{}")
    except ValueError:
        return []
    pins = data.get("pins") or (data.get("object") or {}).get("pins") or []
    out = []
    for p in pins:
        name = p.get("identity") or p.get("package") or ""
        state = p.get("state") or {}
        out.append({"name": name, "version": state.get("version") or state.get("branch") or (state.get("revision") or "")[:12],
                    "url": p.get("location") or p.get("repositoryURL") or "", "source": rel})
    return out


def _podfile_lock(full, rel):
    text = read_text(full) or ""
    section = text.split("DEPENDENCIES:")[0]
    out = []
    for m in re.finditer(r"(?m)^  - \"?([A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)?)\s+\(([^)]+)\)", section):
        if "/" in m.group(1):
            continue
        out.append({"name": m.group(1), "version": m.group(2), "source": rel})
    return out


def _maestro_flows(root):
    flows = []
    for rel, full in walk(root, {".yaml", ".yml"}):
        if "maestro" not in rel.lower() and not rel.startswith(("e2e/", "flows/")):
            continue
        text = read_text(full) or ""
        if re.search(r"(?m)^appId\s*:", text) and re.search(r"(?m)^-\s*(launchApp|tapOn|assertVisible|runFlow|inputText)", text):
            flows.append(rel)
    return flows
