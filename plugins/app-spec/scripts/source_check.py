#!/usr/bin/env python3
"""Record and verify that app-spec source folders stay unchanged during a run."""

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from speclib.common import write_json


STATE = Path("devin") / "source-state.json"


def git_output(path, *args):
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout if result.returncode == 0 else None


def file_fingerprint(path):
    root = Path(os.path.realpath(path))
    if not root.is_dir():
        raise ValueError(f"source folder does not exist: {path}")
    records = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name for name in dirs
            if name != ".git" and not os.path.islink(os.path.join(base, name))
        )
        for name in sorted(files):
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if rel == ".git" or rel.startswith(".git/"):
                continue
            stat = os.stat(full, follow_symlinks=False)
            records.append((rel, stat.st_size, stat.st_mtime_ns))
    encoded = json.dumps(sorted(records), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def folder_state(path):
    absolute = os.path.abspath(path)
    if not os.path.isdir(absolute):
        raise ValueError(f"source folder does not exist: {absolute}")
    if git_output(absolute, "rev-parse", "--show-toplevel") is None:
        return {"path": absolute, "kind": "files", "sha256": file_fingerprint(absolute)}
    head = git_output(absolute, "rev-parse", "HEAD")
    status = git_output(absolute, "status", "--porcelain=v1", "-uall")
    if head is None or status is None:
        raise ValueError(f"could not read git state for {absolute}")
    lines = status.splitlines()
    return {
        "path": absolute,
        "kind": "git",
        "head": head.strip(),
        "status_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
        "status_lines": lines,
    }


def source_paths(out):
    with (Path(out) / "app-spec.json").open(encoding="utf-8") as source:
        config = json.load(source)
    if not isinstance(config, dict):
        raise ValueError("app-spec.json must contain an object")
    app = config.get("app")
    app_path = app.get("path") if isinstance(app, dict) else None
    if not isinstance(app_path, str) or not app_path:
        raise ValueError("app-spec.json must contain app.path")
    paths = [app_path]
    contracts = config.get("contracts", [])
    if contracts is not None:
        if not isinstance(contracts, list):
            raise ValueError("app-spec.json contracts must be a list")
        paths.extend(
            contract["path"]
            for contract in contracts
            if isinstance(contract, dict) and isinstance(contract.get("path"), str) and contract["path"]
        )
    unique = []
    seen = set()
    for path in paths:
        absolute = os.path.abspath(path)
        identity = os.path.realpath(absolute)
        if identity not in seen:
            unique.append(absolute)
            seen.add(identity)
    return unique


def save(out):
    records = [folder_state(path) for path in source_paths(out)]
    state_path = Path(out) / STATE
    write_json(str(state_path), {"version": 1, "folders": records})
    print(f"Saved source state for {len(records)} folder(s)")
    return 0


def porcelain_diff(before, after):
    old = Counter(before)
    new = Counter(after)
    removed = sorted((old - new).elements())
    added = sorted((new - old).elements())
    return [*(f"  - {line}" for line in removed), *(f"  + {line}" for line in added)]


def verify(out):
    state_path = Path(out) / STATE
    if not state_path.is_file():
        print(f"error: no saved source state at {state_path}", file=sys.stderr)
        return 2
    with state_path.open(encoding="utf-8") as source:
        saved = json.load(source)
    if not isinstance(saved, dict) or not isinstance(saved.get("folders"), list):
        raise ValueError(f"invalid source state: {state_path}")
    old = {record.get("path"): record for record in saved["folders"] if isinstance(record, dict)}
    current_paths = source_paths(out)
    changed = False
    for path in current_paths:
        before = old.pop(path, None)
        if before is None:
            print(f"Changed folder: {path} (not in saved state)")
            changed = True
            continue
        after = folder_state(path) if os.path.isdir(path) else {"path": path, "kind": "missing"}
        if before == after:
            continue
        print(f"Changed folder: {path}")
        changed = True
        if before.get("kind") == "git" and after.get("kind") == "git":
            if before.get("head") != after.get("head"):
                print(f"  HEAD: {before.get('head')} -> {after.get('head')}")
            lines = porcelain_diff(before.get("status_lines", []), after.get("status_lines", []))
            for line in lines:
                print(line)
            if not lines and before.get("status_sha256") != after.get("status_sha256"):
                print(f"  status: {before.get('status_sha256')} -> {after.get('status_sha256')}")
        elif before.get("kind") == "files" and after.get("kind") == "files":
            print(f"  files: {before.get('sha256')} -> {after.get('sha256')}")
        else:
            print(f"  kind: {before.get('kind')} -> {after.get('kind')}")
    for path in sorted(old):
        print(f"Changed folder: {path} (removed from app-spec.json)")
        changed = True
    return 1 if changed else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in {"save", "verify"}:
        print("usage: source_check.py save|verify OUT", file=sys.stderr)
        return 2
    action, out = argv
    out = os.path.abspath(out)
    try:
        return save(out) if action == "save" else verify(out)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
