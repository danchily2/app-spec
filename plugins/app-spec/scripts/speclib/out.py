"""Read and write the files of an app-spec output folder."""

import json
import os

from .common import die, load_json

CONFIG = "app-spec.json"


def load_config(out):
    """The run configuration in `out`. Exit 2 when `out` is not an app-spec output folder."""
    path = os.path.join(out, CONFIG)
    if not os.path.isfile(path):
        die(f"{out} is not an app-spec output folder ({CONFIG} not found)")
    cfg = load_json(path)
    if not isinstance(cfg, dict):
        die(f"{path} is not an app-spec output folder configuration (invalid JSON)")
    return cfg


def load(out, name, default=None):
    """The parsed JSON of `name` in `out`, or `default` when the file is missing or invalid."""
    return load_json(os.path.join(out, name), default)


def save(out, name, data):
    """Write `data` as JSON (two-space indent, UTF-8, trailing newline). Return the path."""
    return save_text(out, name, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def save_text(out, name, text):
    """Write `text` to `name` in `out`, creating folders. Return the path."""
    path = os.path.join(out, name)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def rel(app_root, path):
    """`path` relative to `app_root`, with forward slashes."""
    return os.path.relpath(path, app_root).replace(os.sep, "/")


def app_root(cfg):
    """The absolute app path recorded in the configuration."""
    return cfg["app"]["path"]
