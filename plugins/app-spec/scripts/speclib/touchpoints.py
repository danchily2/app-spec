"""Touch points: the files outside a module that use it or that it needs.

A touch point is found by name. Names the core declares (types, requests, screens, event families) and the string
keys it uses are searched for in every other source file. A file gets one reason, the first that matches, in this
order: uses type, uses request, uses string key, routes into a screen, fires an event family.

Only a top-level declaration is matched by its bare name. A type nested in another one (`ViewModel`, `Delegate` or
`Destination` inside a TCA feature) is matched only in its qualified form, such as `PayslipFeature.Destination`, since
almost every feature of an app nests a type of the same name. A name that a file outside the core declares too, such
as another package's own `Loadable` or `AnalyticsFeature`, is ambiguous and is not matched. An event family counts only when the core declares it:
a family the core only uses, such as an app-wide `EmployeeAnalytics`, would make every file that logs an event a touch
point.
"""

import os
import re

from .common import SOURCE_EXT, read_text, strip_comments, walk

STACK_EXTS = {
    "ios-native": {".swift", ".m", ".mm", ".h"},
    "android-native": {".kt", ".kts", ".java"},
    "react-native": {".ts", ".tsx", ".js", ".jsx"},
}

# Names too common to say anything when they appear in another file.
# Compared in lower case.
GENERIC_NAMES = {"state", "action", "event", "events", "model", "models", "items", "error", "result", "config",
                 "props", "style", "styles", "theme", "route", "routes", "types", "utils", "helper", "helpers",
                 "index", "default",
                 # types that iOS (TCA, MVVM, coordinators) and Android features nest under the same name
                 "viewmodel", "delegate", "destination", "cancelid", "alert", "mapper", "cellmodel", "segment",
                 "direction", "path", "coordinator", "feature", "dependencies", "environment", "reducer", "view",
                 "body"}
MIN_NAME = 5

_DECL = {
    "ios-native": re.compile(r"\b(?:struct|class|enum|protocol|actor)\s+([A-Z]\w*)([^{\n]*)"),
    "android-native": re.compile(r"\b(?:class|interface|object|enum)\s+([A-Z]\w*)([^{\n]*)"),
    "react-native": re.compile(
        r"\bexport\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
        r"(?:const|let|function|class|interface|type|enum)\s+([A-Za-z_]\w*)([^{=\n]*)"),
}
# a declaration that opens a scope, with the text up to its brace: names the scope a nested declaration lives in
_SCOPE_HEAD = re.compile(r"\b(?:struct|class|enum|protocol|actor|extension|interface|object)\s+([A-Z][\w.]*)[^{};]*$")
_COMPOSABLE = re.compile(r"@Composable\s+(?:internal\s+|private\s+)?fun\s+([A-Z]\w*)")
_SCREEN_NAME = re.compile(r"(?:View|ViewController|Screen|Fragment|Activity|Page|Scene)$")
_SCREEN_BASE = re.compile(r"\b(?:View|UIViewController|Screen|Fragment|AppCompatActivity|ComponentActivity)\b")
_REQUEST = re.compile(r"Request\b")
_EVENT_FAMILY = re.compile(r"\b[A-Z]\w*(?:Events?|Analytics|Tracking)\b")
_NAV = re.compile(r"\b(?:push|present|navigate|navigationDestination|NavigationLink|startActivity|composable|tabItem|"
                  r"fullScreenCover|sheet)\b|\bIntent\(")
_LITERAL = re.compile(r"[\"']([^\"'\\\n]{1,160})[\"']")
_ANDROID_REF = re.compile(r"\bR\.string\.(\w+)|@string/(\w+)")


def source_exts(stack):
    return STACK_EXTS.get(stack, SOURCE_EXT)


def _clean(text):
    return strip_comments(text)


def _scopes(text):
    """The enclosing type path at each offset: a sorted list of (offset, path) where path is a tuple of names, or None
    for a block that is not a type (a function or closure body), in force from that offset on."""
    changes, stack, last = [(0, ())], [], 0
    for m in re.finditer(r"[{};]", text):
        ch, i = m.group(0), m.start()
        if ch == "{":
            head = _SCOPE_HEAD.search(text, last, i)
            stack.append(head.group(1) if head else None)
        elif ch == "}" and stack:
            stack.pop()
        last = i + 1
        if ch != ";":
            changes.append((i + 1, None if None in stack else tuple(n for part in stack for n in part.split("."))))
    return changes


def _scope_at(changes, offset):
    path = ()
    for start, value in changes:
        if start > offset:
            break
        path = value
    return path


def declared(stack, text):
    """What one file declares: {"types": set, "requests": set, "screens": set, "families": set}.

    A top-level name is kept as is. A name nested in a type is kept qualified (`Outer.Inner`), and one declared inside
    a function body is dropped."""
    found = {"types": set(), "requests": set(), "screens": set(), "families": set()}
    pattern = _DECL.get(stack)
    names = []
    nests = stack in ("ios-native", "android-native")
    changes = _scopes(text) if nests else [(0, ())]
    if pattern:
        names += [(m.group(1), m.group(2) or "", m.start()) for m in pattern.finditer(text)]
    if stack == "android-native":
        names += [(m.group(1), "", m.start()) for m in _COMPOSABLE.finditer(text)]
    for name, rest, at in names:
        outer = _scope_at(changes, at)
        if outer is None:
            continue  # a local type of a function body is not reachable from another file
        if outer:
            qualified = ".".join(outer + (name,))
        elif len(name) < MIN_NAME or name.lower() in GENERIC_NAMES:
            continue
        else:
            qualified = name
        if stack == "react-native" and name[0].islower() and not re.match(r"use[A-Z]", name):
            continue  # a lowercase export that is neither a hook nor a component is a helper or a constant
        if _EVENT_FAMILY.fullmatch(name):
            found["families"].add(qualified)
        elif _REQUEST.search(name) or _REQUEST.search(rest):
            found["requests"].add(qualified)
        elif name[0].isupper() and (_SCREEN_NAME.search(name) or _SCREEN_BASE.search(rest)):
            found["screens"].add(qualified)
        else:
            found["types"].add(qualified)
    return found


def string_literals(text):
    """Every string key a file could be using: quoted literals and Android resource references."""
    keys = set(m.group(1) for m in _LITERAL.finditer(text))
    for m in _ANDROID_REF.finditer(text):
        keys.add(m.group(1) or m.group(2))
    return keys


def _abs(app_root, path):
    return path if os.path.isabs(path) else os.path.join(app_root, path)


def _rel(app_root, path):
    full = os.path.realpath(path)
    return os.path.relpath(full, os.path.realpath(app_root)).replace(os.sep, "/")


def _first(regex, text):
    m = regex.search(text) if regex else None
    return m.group(0) if m else None


def _words(names):
    """One regex that matches any of the names as a whole word, or None when there are none.

    A qualified name (`Outer.Inner`) must not be preceded by a dot either, so `Other.Outer.Inner` does not match."""
    names = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w.])(?:" + "|".join(re.escape(n) for n in names) + r")\b") if names else None


def find(app_root, stack, core_files, string_keys, keyword=None):
    """The files outside the core that touch it, as [{"file": rel, "reason": str}] in path order.

    With `keyword`, only files whose text contains the word (case-insensitively) are kept."""
    core = set(_rel(app_root, _abs(app_root, f)) for f in core_files)
    decl = {"types": set(), "requests": set(), "screens": set(), "families": set()}
    for rel in sorted(core):
        text = read_text(_abs(app_root, rel))
        if text is None:
            continue
        for kind, names in declared(stack, _clean(text)).items():
            decl[kind] |= names
    keys = set(string_keys)
    wanted = keyword.lower() if keyword else None

    files = []
    elsewhere = set()  # top-level names that a file outside the core declares too, such as its own Loadable
    for rel, full in walk(app_root, source_exts(stack), include_tests=False):
        if rel in core:
            continue
        raw = read_text(full)
        if raw is None:
            continue
        text = _clean(raw)
        files.append((rel, raw, text))
        elsewhere |= set().union(*declared(stack, text).values())
    for kind in decl:
        decl[kind] -= elsewhere
    type_re, request_re, family_re = _words(decl["types"]), _words(decl["requests"]), _words(decl["families"])
    screen_re = _words(set(decl["screens"]) | set(n[:-6] for n in decl["screens"]
                                                  if n.endswith("Screen") and len(n.rsplit(".", 1)[-1]) - 6 >= MIN_NAME))

    found = []
    for rel, raw, text in files:
        if wanted and wanted not in raw.lower():
            continue
        reason = None
        name = _first(type_re, text)
        if name:
            reason = f"uses type {name}"
        if not reason:
            name = _first(request_re, text)
            reason = f"uses request {name}" if name else None
        if not reason:
            hit = sorted(keys & string_literals(text))
            reason = f"uses string key {hit[0]}" if hit else None
        if not reason and screen_re:
            for line in text.splitlines():
                m = screen_re.search(line)
                if m and _NAV.search(line):
                    reason = f"routes into {_screen_of(m.group(0), decl['screens'])}"
                    break
        if not reason:
            name = _first(family_re, text)
            reason = f"fires event family {name}" if name else None
        if reason:
            found.append({"file": rel, "reason": reason})
    return found


def _screen_of(matched, screens):
    """The core screen a matched word names: the word itself, or the screen whose name ends in 'Screen' after it."""
    return matched if matched in screens else next((s for s in sorted(screens) if s == matched + "Screen"), matched)
