"""Check that the `path:line` citations inside catalog entries lie within their files.

Agents sometimes cite a range that runs past the end of the file (`GetPayslips.swift:14-70` in a 55-line file). The
grader only reads the rendered spec, and some catalog values (contract field sources, rule edge cases) are not
rendered as citations, so `render.py catalogs` and `merge_contracts.py` check every string of the catalogs here and
report what does not resolve in `render-warnings.json`. Standard library only.
"""

import os
import re

from . import paths

# a citation-shaped token: a path with a file extension, then :line or :line-line
_CITE = re.compile(r"(?:^|(?<=[\s`'\"(\[{,=;]))(~?/?[\w@+.\-]+(?:/[\w@+.\-]+)*\.[A-Za-z][\w]*):(\d+)(?:-(\d+))?(?![\w-])")


class Ranges:
    """Line counts of the files under the app root and the contract roots of one run."""

    def __init__(self, cfg):
        self.root_list = paths.roots(cfg)
        self._lengths = {}

    def length(self, rel):
        """The number of lines of `rel` (relative, absolute or behind a root name), or `None` when no root holds it."""
        rel = paths.relative_path(rel, self.root_list)
        for real, _ in self.root_list:
            full = os.path.realpath(os.path.join(real, rel))
            try:
                inside = os.path.commonpath([real, full]) == real
            except ValueError:
                inside = False
            if inside and os.path.isfile(full):
                if full not in self._lengths:
                    try:
                        with open(full, "rb") as fh:
                            data = fh.read()
                    except OSError:
                        return None
                    self._lengths[full] = data.count(b"\n") + (0 if not data or data.endswith(b"\n") else 1)
                return self._lengths[full]
        return None

    def problem(self, path, first, last):
        """Why `path:first-last` does not resolve, or `None`."""
        length = self.length(path)
        if length is None:
            return "file not found"
        if first < 1 or last < first:
            return "not a line range"
        if last > length:
            return f"the file has {length} lines"
        return None

    def problems(self, value):
        """`[(citation, reason)]` for every citation in the strings of a JSON value that does not resolve, once each."""
        found, seen = [], set()
        for text in _strings(value):
            for m in _CITE.finditer(text):
                cite = m.group(0)
                if cite in seen:
                    continue
                seen.add(cite)
                first = int(m.group(2))
                last = int(m.group(3) or m.group(2))
                reason = self.problem(m.group(1), first, last)
                if reason:
                    found.append((cite, reason))
        return found


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
