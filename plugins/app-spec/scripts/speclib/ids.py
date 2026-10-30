"""The id registry: keys to ids that stay the same across runs, and the key normalizer."""

import os
import re

import json

from .common import die, write_json

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
        data = {}
        if os.path.exists(path):  # a missing file starts a new registry; an unreadable one must never restart numbering
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                die(f"{path} cannot be read ({exc.__class__.__name__}); fix or remove it, ids would restart at 001")
            if not isinstance(data, dict):
                die(f"{path} is not a JSON object; fix or remove it, ids would restart at 001")
        self.data = data
        for prefix in PREFIXES:
            if not isinstance(self.data.get(prefix), dict):
                self.data[prefix] = {}
        if not isinstance(self.data.get("max"), dict):
            self.data["max"] = {}
        if not isinstance(self.data.get("UCfiles"), dict):
            self.data["UCfiles"] = {}  # files of each use case id, to recognise a renamed use case

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

    def adopt(self, prefix, key, id_):
        """Record `key` as another name of the existing `id_` without issuing a number."""
        self.data.setdefault(prefix, {})[key] = id_

    def save(self):
        """Write the registry to its path."""
        write_json(os.fspath(self.path), self.data)
