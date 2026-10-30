"""Native Android inventory: Gradle modules, manifests (permissions, deep links, exported components), screens
(activities, fragments, screen composables), Retrofit/Ktor endpoints, analytics, storage, strings, tests and
dependencies. Every count is returned with the rule that produced it.
"""

import os
import re
import xml.etree.ElementTree as ET

from . import notify
from . import strings as strcat
from .common import (is_test_path, line_of, looks_like_path, normalize_endpoint, read_text, sanitize_url,
                     strip_comments, walk)

A = "{http://schemas.android.com/apk/res/android}"

_KT_STRING = r'"(?:[^"\\\n]|\\.)*"'
_RETROFIT = re.compile(r"@(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(\s*(?:value\s*=\s*)?(" + _KT_STRING + r")")
_RETROFIT_HTTP = re.compile(r"@HTTP\s*\(\s*method\s*=\s*\"([A-Z]+)\"\s*,\s*path\s*=\s*(" + _KT_STRING + r")")
_KTOR = re.compile(r"\b(?:client|httpClient|http)\s*\.\s*(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*(" + _KT_STRING + r")")
_OKHTTP = re.compile(r"\.url\s*\(\s*(" + _KT_STRING + r")")
_ACTIVITY = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*((?:[A-Za-z_][A-Za-z0-9_.]*)?Activity)\b")
_FRAGMENT = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*((?:[A-Za-z_][A-Za-z0-9_.]*)?Fragment)\b")
_COMPOSABLE = re.compile(r"@Composable\s+(?:(?:internal|private|public)\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*(?:Screen|Page|Route))\s*\(")
_LOG_EVENT = re.compile(r"\b(?:logEvent|trackEvent|track)\s*\(\s*(" + _KT_STRING + r")")
_PREFS = re.compile(r"\b(?:getSharedPreferences|stringPreferencesKey|booleanPreferencesKey|intPreferencesKey|longPreferencesKey|putString|putBoolean|putInt|putLong|getString|getBoolean|getInt|getLong)\s*\(\s*(" + _KT_STRING + r")")
_ROOM = re.compile(r"@Entity\s*(?:\(([^)]*)\))?\s*(?:data\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)")
_CONST = re.compile(r"\bconst\s+val\s+([A-Z][A-Z0-9_]*)\s*(?::\s*String\s*)?=\s*(" + _KT_STRING + r")")
_TEMPLATE = re.compile(r"\$\{([^}]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
_WEB = re.compile(r"\b(?:Uri\.parse|toUri|CustomTabsIntent[^\n]*launchUrl[^\n]*?Uri\.parse)\s*\(\s*(" + _KT_STRING + r")")


def _lit(s):
    return s[1:-1] if s and s[0] == '"' else s


def _gradle_values(root):
    """Application ids (single or double quotes, flavors included), else the namespace of an app module, and the SDK
    levels from every build.gradle(.kts)."""
    app_ids, namespaces, min_sdk, target_sdk = [], [], [], []
    for rel, full in walk(root, {".gradle", ".kts"}):
        if not os.path.basename(rel).startswith("build.gradle"):
            continue
        text = read_text(full) or ""
        app_ids += re.findall(r"\bapplicationId\s*=?\s*[\"']([^\"']+)[\"']", text)
        if "com.android.application" in text or re.search(r"\bapplicationId\b", text):
            namespaces += re.findall(r"\bnamespace\s*=?\s*[\"']([^\"']+)[\"']", text)
        min_sdk += re.findall(r"\bminSdk(?:Version)?\s*=?\s*\(?\s*(\d+)", text)
        target_sdk += re.findall(r"\btargetSdk(?:Version)?\s*=?\s*\(?\s*(\d+)", text)
    return sorted(set(app_ids) or set(namespaces)), sorted({int(x) for x in min_sdk}), sorted({int(x) for x in target_sdk})


def platform(root, rel_prefix=""):
    """Platform facts of the Android side of an app (a native app root, or a React Native app's android/ folder)."""
    root = os.path.realpath(root)
    out = {"bundleIds": [], "urlSchemes": [], "associatedDomains": [], "backgroundModes": [], "permissions": [],
           "extensions": [], "appGroups": [], "keychainGroups": [], "push": False, "minOS": {}, "entitlements": [],
           "exported": [], "deepLinks": [], "cleartext": [], "manifests": [], "appLinkHosts": []}
    if not os.path.isdir(root):
        return out
    app_ids, min_sdk, _ = _gradle_values(root)
    out["bundleIds"] = app_ids
    if min_sdk:
        out["minOS"]["android"] = min(min_sdk)
    for rel, full in walk(root, {".xml"}):
        if os.path.basename(rel) != "AndroidManifest.xml" or "/src/main/" not in f"/{rel}" and not rel.startswith("src/main/"):
            continue
        if is_test_path(rel):
            continue
        out["manifests"].append(rel_prefix + rel)
        try:
            tree = ET.fromstring(read_text(full) or "")
        except ET.ParseError:
            continue
        pkg = tree.get("package")
        if pkg and not app_ids and pkg not in out["bundleIds"]:
            out["bundleIds"].append(pkg)
        for perm in tree.iter("uses-permission"):
            name = perm.get(A + "name")
            if name and not any(p["key"] == name for p in out["permissions"]):
                out["permissions"].append({"key": name, "file": rel_prefix + rel})
        app = tree.find("application")
        if app is not None:
            if app.get(A + "usesCleartextTraffic") == "true":
                out["cleartext"].append(rel_prefix + rel)
            for comp in list(app):
                if comp.tag not in ("activity", "activity-alias", "service", "receiver", "provider"):
                    continue
                name = comp.get(A + "name") or ""
                has_filter = comp.find("intent-filter") is not None
                exported = comp.get(A + "exported")
                if exported == "true" or (exported is None and has_filter):
                    out["exported"].append({"component": comp.tag, "name": name, "file": rel_prefix + rel})
                if comp.tag == "service" and "FirebaseMessagingService" in (name + ET.tostring(comp, encoding="unicode")):
                    out["push"] = True
                for f in comp.findall("intent-filter"):
                    actions = [a.get(A + "name") for a in f.findall("action")]
                    cats = [c.get(A + "name") for c in f.findall("category")]
                    if "com.google.firebase.MESSAGING_EVENT" in actions:
                        out["push"] = True
                    if "android.intent.action.VIEW" not in actions:
                        continue
                    for d in f.findall("data"):
                        scheme, host = d.get(A + "scheme"), d.get(A + "host")
                        path = d.get(A + "pathPrefix") or d.get(A + "path") or d.get(A + "pathPattern") or ""
                        link = {"scheme": scheme, "host": host, "path": path, "component": name,
                                "autoVerify": f.get(A + "autoVerify") == "true",
                                "browsable": "android.intent.category.BROWSABLE" in cats}
                        out["deepLinks"].append(link)
                        if scheme and scheme not in ("http", "https") and scheme not in out["urlSchemes"]:
                            out["urlSchemes"].append(scheme)
                        if scheme in ("http", "https") and host and host not in out["appLinkHosts"]:
                            out["appLinkHosts"].append(host)
    return out


def extract(root):
    root = os.path.realpath(root)
    texts = {}
    consts = {}
    for rel, full in walk(root, {".kt", ".java", ".kts"}):
        text = read_text(full)
        if text is None:
            continue
        clean = strip_comments(text)
        texts[rel] = clean
        for m in _CONST.finditer(clean):
            consts.setdefault(m.group(1), set()).add(_lit(m.group(2)))

    def resolve(raw):
        def sub(m):
            name = (m.group(1) or m.group(2) or "").split(".")[-1]
            vals = consts.get(name)
            return next(iter(vals)) if vals and len(vals) == 1 else "{}"
        return _TEMPLATE.sub(sub, raw)

    screens, endpoints, events, storage, web_links = [], [], [], [], []
    test_files, ui_test_files, frameworks = 0, 0, set()
    for rel, text in texts.items():
        if is_test_path(rel) or "/src/test/" in f"/{rel}" or "/src/androidTest/" in f"/{rel}":
            if rel.endswith((".kt", ".java")):
                test_files += 1
                if "/androidTest/" in f"/{rel}":
                    ui_test_files += 1
                for fw, pat in (("JUnit", r"import\s+org\.junit"), ("Espresso", r"androidx\.test\.espresso"),
                                ("Compose UI test", r"androidx\.compose\.ui\.test"), ("Robolectric", r"org\.robolectric"),
                                ("MockK", r"io\.mockk"), ("Kotest", r"io\.kotest")):
                    if re.search(pat, text):
                        frameworks.add(fw)
            continue
        area = rel.split("/")[0]
        for pat, kind in ((_ACTIVITY, "activity"), (_FRAGMENT, "fragment")):
            for m in pat.finditer(text):
                screens.append({"name": m.group(1), "file": f"{rel}:{line_of(text, m.start())}", "area": area, "kind": kind})
        for m in _COMPOSABLE.finditer(text):
            screens.append({"name": m.group(1), "file": f"{rel}:{line_of(text, m.start())}", "area": area, "kind": "composable"})
        for m in _RETROFIT.finditer(text):
            raw = resolve(_lit(m.group(2)))
            path = normalize_endpoint(raw)
            if path:
                endpoints.append({"method": m.group(1), "path": path, "raw": raw[:200], "client": "retrofit",
                                  "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _RETROFIT_HTTP.finditer(text):
            raw = resolve(_lit(m.group(2)))
            path = normalize_endpoint(raw)
            if path:
                endpoints.append({"method": m.group(1), "path": path, "raw": raw[:200], "client": "retrofit",
                                  "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _KTOR.finditer(text):
            raw = resolve(_lit(m.group(2)))
            if looks_like_path(raw) and normalize_endpoint(raw):
                endpoints.append({"method": m.group(1).upper(), "path": normalize_endpoint(raw), "raw": raw[:200],
                                  "client": "ktor", "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _OKHTTP.finditer(text):
            raw = resolve(_lit(m.group(1)))
            if looks_like_path(raw) and normalize_endpoint(raw):
                endpoints.append({"method": None, "path": normalize_endpoint(raw), "raw": raw[:200], "client": "okhttp",
                                  "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _LOG_EVENT.finditer(text):
            events.append({"name": _lit(m.group(1)), "family": "call", "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _WEB.finditer(text):
            val = resolve(_lit(m.group(1)))
            if re.match(r"^https?://", val, re.I):
                web_links.append({"url": sanitize_url(val)[:300], "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _PREFS.finditer(text):
            storage.append({"kind": "preferences", "key": _lit(m.group(1)), "file": f"{rel}:{line_of(text, m.start())}"})
        for m in _ROOM.finditer(text):
            table = re.search(r"tableName\s*=\s*\"([^\"]+)\"", m.group(1) or "")
            storage.append({"kind": "room-entity", "key": table.group(1) if table else m.group(2),
                            "file": f"{rel}:{line_of(text, m.start())}"})
        if "EncryptedSharedPreferences" in text or "KeyStore.getInstance(\"AndroidKeyStore\")" in text:
            storage.append({"kind": "keystore", "key": "encrypted storage", "file": rel})

    modules = []
    for rel, full in walk(root, {".gradle", ".kts"}):
        if os.path.basename(rel) in ("settings.gradle", "settings.gradle.kts"):
            text = read_text(full) or ""
            for m in re.finditer(r"include\s*\(?([^\n)]*)", text):
                modules += [x for x in re.findall(r"['\"](:[^'\"]+)['\"]", m.group(1)) if x not in modules]

    string_files = [rel for rel, _ in walk(root, {".xml"}) if "/res/values" in f"/{rel}" and not is_test_path(rel)]
    catalog = strcat.parse_android_strings(root, string_files) or strcat.combine()

    deps, seen = [], set()
    for rel, full in walk(root, {".gradle", ".kts", ".toml"}):
        text = read_text(full) or ""
        if rel.endswith(".toml") and "versions" in os.path.basename(rel):
            for m in re.finditer(r"(?m)^\s*([A-Za-z0-9_.-]+)\s*=\s*\{[^}]*module\s*=\s*\"([^\"]+)\"[^}]*\}", text):
                if m.group(2) not in seen:
                    seen.add(m.group(2))
                    deps.append({"name": m.group(2), "version": "", "source": rel})
            continue
        for m in re.finditer(r"(?:implementation|api|kapt|ksp)\s*\(?\s*[\"']([A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+)(?::([^\"']+))?[\"']", text):
            if m.group(1) not in seen:
                seen.add(m.group(1))
                deps.append({"name": m.group(1), "version": m.group(2) or "", "source": rel})

    maestro = []
    for rel, full in walk(root, {".yaml", ".yml"}):
        if "maestro" in rel.lower():
            text = read_text(full) or ""
            if re.search(r"(?m)^appId\s*:", text):
                maestro.append(rel)

    plat = platform(root)
    plat["notificationCategories"] = notify.scan(root)
    uniq_paths = {e["path"] for e in endpoints}
    counts = {
        "sourceFiles": sum(1 for rel in texts if not is_test_path(rel) and "/src/test/" not in f"/{rel}" and "/src/androidTest/" not in f"/{rel}"),
        "screens": len(screens),
        "endpoints": len(uniq_paths),
        "events": len({e["name"] for e in events}),
        "stringKeys": len(catalog["keys"]),
        "locales": len(catalog["locales"]),
        "storageKeys": len(storage),
        "webLinks": len({w["url"] for w in web_links}),
        "testFiles": test_files,
        "maestroFlows": len(maestro),
        "packages": len(modules),
        "dependencies": len(deps),
        "targets": len(plat["manifests"]),
    }
    rules = {
        "sourceFiles": "non-test .kt, .java and .kts files, generated and build directories excluded",
        "screens": "classes extending *Activity or *Fragment plus @Composable functions named *Screen/*Page/*Route, outside test source sets",
        "endpoints": "distinct normalized paths from Retrofit @GET/@POST/@PUT/@DELETE/@PATCH/@HEAD/@HTTP annotations with a literal path, Ktor client calls and OkHttp .url() literals; const val templates resolved",
        "events": "distinct string literals passed to logEvent/trackEvent/track",
        "stringKeys": "<string> and <plurals> names in res/values*/ XML (union of locales; values-night and other non-locale qualifiers ignored)",
        "locales": "values-<locale> folders holding strings (default counts as one)",
        "storageKeys": "SharedPreferences and DataStore key literals, Room @Entity classes, one row per file using EncryptedSharedPreferences or the Android KeyStore",
        "webLinks": "absolute http(s) URLs passed to Uri.parse/toUri (help, legal and marketing pages)",
        "testFiles": ".kt/.java files under src/test or src/androidTest (or other test paths)",
        "maestroFlows": "YAML files under a maestro folder with an appId: header",
        "packages": "modules named in include(...) of settings.gradle(.kts)",
        "dependencies": "distinct group:artifact coordinates in Gradle files and version catalogs",
        "targets": "AndroidManifest.xml files under src/main",
    }
    notes = [
        "Endpoints whose path comes from @Url parameters or runtime values have no literal and are not counted.",
        "Navigation destinations defined in Compose NavHost builders are found only through *Screen composables.",
    ]
    return {
        "stack": "android-native", "counts": counts, "rules": rules, "screens": screens, "routes": [],
        "endpoints": endpoints, "webLinks": web_links, "events": events, "storage": storage, "platform": plat, "dependencies": deps,
        "localPackages": [{"name": m, "file": "settings.gradle"} for m in modules],
        "tests": {"frameworks": sorted(frameworks), "unitTestFiles": test_files - ui_test_files, "uiTestFiles": ui_test_files,
                  "maestroFlows": len(maestro), "maestro": maestro},
        "strings": catalog, "notes": notes,
    }
