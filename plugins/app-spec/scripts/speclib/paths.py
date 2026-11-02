"""Citation paths relative to a root.

Agents cite `path:line` in three shapes: relative to the app root or a contract root (the only shape the grader
resolves), absolute (`/Users/me/code/me-api/Controllers/X.cs:12`), or behind the root folder's name
(`me-api/Controllers/X.cs:12`). `relativize` rewrites the last two into the first, in every string of a JSON value.
A fourth shape is relative to a folder inside the root (`PayslipsFeature/PayslipItem.swift:10`); `complete` rewrites it
to the one real file whose path ends with it.
"""

import os
import re

# a path-shaped token: it starts at the beginning, after a space, quote, backtick, bracket, comma or `=`
_TOKEN = re.compile(r"(?:^|(?<=[\s`'\"(\[{,=]))(~?/?[\w@+.\-]+(?:/[\w@+.\-]+)+)")


def roots(cfg):
    """[(real root path, [names it may be cited by])] for the app and each contract repository of app-spec.json."""
    found = []
    app = (cfg or {}).get("app") or {}
    entries = [(app.get("path"), [app.get("name")])]
    entries += [(c.get("path"), [c.get("name")]) for c in (cfg or {}).get("contracts") or [] if isinstance(c, dict)]
    for path, names in entries:
        if not path:
            continue
        real = os.path.realpath(str(path))
        names = {str(n) for n in names if n} | {os.path.basename(real.rstrip(os.sep))}
        found.append((real, sorted(n for n in names if n)))
    return found


def _prefixes(real):
    """The absolute spellings of one root: as given, its real path and with `~` for the home folder."""
    spellings = {real}
    home = os.path.realpath(os.path.expanduser("~"))
    if real.startswith(home + os.sep):
        spellings.add("~" + real[len(home):])
    if real.startswith("/private/"):  # macOS: /private/tmp is /tmp and /private/var is /var
        spellings.add(real[len("/private"):])
    return sorted(spellings, key=len, reverse=True)


def _exists(root, rel):
    return os.path.exists(os.path.join(root, re.sub(r":\d[\d\-]*$", "", rel)))


def relative_path(token, root_list):
    """`token` rewritten relative to the root it lies under, or `token` unchanged."""
    for real, names in root_list:
        for prefix in _prefixes(real):
            if token.startswith(prefix + "/"):
                return token[len(prefix) + 1:]
    if token.startswith(("/", "~")):
        return token
    for real, names in root_list:
        for name in names:
            rest = token[len(name) + 1:] if token.startswith(name + "/") else None
            # a leading root name goes only when the path exists without it and not with it
            if rest and _exists(real, rest) and not _exists(real, token):
                return rest
    return token


_SKIP_DIRS = {"node_modules", "Pods", "build", "DerivedData"}


def file_index(root_list):
    """{file name: [paths relative to their root]} of every file under the roots, hidden and build folders left out."""
    names = {}
    for real, _ in root_list:
        for base, dirs, files in os.walk(real):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in _SKIP_DIRS]
            for f in files:
                names.setdefault(f, []).append(os.path.relpath(os.path.join(base, f), real))
    return names


def complete(value, root_list, index):
    """`value` (a string or a list of strings) with every path that names no file under a root, but names the end of
    exactly one file in `index` (from `file_index`), rewritten to that file's full relative path. Other paths stay."""
    if isinstance(value, list):
        return [complete(v, root_list, index) for v in value]
    if not isinstance(value, str):
        return value

    def fix(m):
        cited = m.group(1)
        if cited.startswith(("/", "~")) or "." not in cited.rsplit("/", 1)[-1]:
            return cited
        if any(_exists(real, cited) for real, _ in root_list):
            return cited
        matches = {p for p in index.get(cited.rsplit("/", 1)[-1], []) if p.endswith("/" + cited)}
        return matches.pop() if len(matches) == 1 else cited

    return _TOKEN.sub(fix, value)


def relativize(value, root_list):
    """`value` (a JSON value) with every path-shaped token of every string rewritten relative to its root."""
    if isinstance(value, str):
        return _TOKEN.sub(lambda m: relative_path(m.group(1), root_list), value)
    if isinstance(value, list):
        return [relativize(v, root_list) for v in value]
    if isinstance(value, dict):
        return {k: relativize(v, root_list) for k, v in value.items()}
    return value
