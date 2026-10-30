"""The id registry: keys to ids that stay the same across runs, and the key normalizer."""

import os
import re

from .common import load_json, write_json

PREFIXES = ("UC", "SCR", "FLOW", "RULE", "EP")
_ARTICLES = {"a", "an", "the"}
_NUMBER = re.compile(r"-(\d+)$")


def norm(text):
    """Lower-case `text`, replace every run of characters other than letters and digits with one space, trim, and
    drop the words `a`, `an` and `the`."""
    words = re.sub(r"[\W_]+", " ", str(text or "").lower()).split()
    return " ".join(w for w in words if w not in _ARTICLES)


class Registry:
    """`ids.json`: one map per prefix from a key to its id, and `max`, the highest number issued per prefix.

    Existing keys keep their ids, a retired key stays in its map, and a new key takes `max + 1`, so no number is
    issued twice."""

    def __init__(self, path):
        self.path = path
        data = load_json(path, {})
        self.data = data if isinstance(data, dict) else {}
        for prefix in PREFIXES:
            if not isinstance(self.data.get(prefix), dict):
                self.data[prefix] = {}
        if not isinstance(self.data.get("max"), dict):
            self.data["max"] = {}

    def _highest(self, prefix):
        """The highest number ever issued for `prefix`: the stored `max`, or a higher number found in the map."""
        found = [int(m.group(1)) for v in self.data.get(prefix, {}).values() if (m := _NUMBER.search(str(v)))]
        stored = self.data["max"].get(prefix, 0)
        return max([stored if isinstance(stored, int) else 0] + found)

    def assign(self, prefix, key):
        """The id of `key` under `prefix`: the existing one, else the next number after the highest ever issued."""
        mapping = self.data.setdefault(prefix, {})
        if key in mapping:
            return mapping[key]
        number = self._highest(prefix) + 1
        mapping[key] = f"{prefix}-{number:03d}"
        self.data["max"][prefix] = number
        return mapping[key]

    def save(self):
        """Write the registry to its path."""
        write_json(os.fspath(self.path), self.data)
