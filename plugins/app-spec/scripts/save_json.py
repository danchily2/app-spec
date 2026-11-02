#!/usr/bin/env python3
"""Save the JSON an agent or a workflow returned to a file of the run folder.

    python3 save_json.py <src> <dest> [--key KEY] [--list]

`src` is a workflow output file (`{"summary": ..., "result": {...}}`), a transcript in JSON Lines (the text of the
assistant messages is read, last message last), a tool result the harness stored as a file because the answer was
too large to show (a JSON list of `{"type": "text", "text": ...}` blocks, read as their joined text) or plain text,
such as an agent's answer saved to a file; `-` reads standard input. The script takes the last JSON value in it: a fenced block (```json ... ``` or ``` ... ```) or a bare
object or list inside prose. With `--key`, only an object that holds KEY at its top level, or a list whose first
object does, is taken. With `--list`, only a list. A `{"result": ...}` wrapper is unwrapped first, also when the result
is a JSON string, unless the object holds KEY itself. The value is written to `dest` as JSON (two-space indent, UTF-8, trailing newline), creating its
folder.

Prints what it wrote. Exit code 2 when `src` cannot be read or holds no matching JSON value. Standard library only.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib.common import die  # noqa: E402

_FENCE = re.compile(r"```[ \t]*(?:json|JSON|jsonc)?[ \t]*\n(.*?)\n?```", re.S)
_DECODER = json.JSONDecoder()


def unwrap(value, key=None):
    """The `result` of a workflow output `{"summary": ..., "result": ...}` (a JSON string result is parsed), else
    `value`. An object that holds `key` itself is never unwrapped. No payload of the run has a top-level `result`."""
    while isinstance(value, dict) and "result" in value and (key is None or key not in value):
        inner = value["result"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                found = values_in(inner)
                inner = found[-1] if found else inner
        value = inner
    return value


def values_in(text):
    """Every JSON object or list in `text`, in order: fenced blocks first claim their span, then bare values. A value
    nested inside another one found is not listed on its own."""
    found, taken = [], []
    for m in _FENCE.finditer(text):
        try:
            found.append((m.start(), json.loads(m.group(1))))
            taken.append((m.start(), m.end()))
        except ValueError:
            continue
    i = 0
    while i < len(text):
        if text[i] in "{[" and not any(a <= i < b for a, b in taken):
            try:
                value, end = _DECODER.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            if isinstance(value, (dict, list)):
                found.append((i, value))
                i = end
                continue
        i += 1
    return [v for _, v in sorted(found, key=lambda x: x[0])]


def _assistant_texts(lines):
    """The text of each assistant message of a JSON Lines transcript, in order. None when `lines` is no transcript."""
    texts, records = [], 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            return None
        if not isinstance(record, dict):
            return None
        records += 1
        message = record.get("message") if isinstance(record.get("message"), dict) else record
        role = message.get("role") or record.get("type")
        if role != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.append("\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"))
    return texts if records > 1 or texts else None


def _text_blocks(value):
    """Whether `value` is a stored tool result: a non-empty list of `{"type": "text", "text": ...}` blocks only."""
    return isinstance(value, list) and bool(value) and all(
        isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str) for b in value)


def candidates(text, key=None):
    """Every JSON value `text` offers, last one last."""
    try:
        whole = json.loads(text)
    except ValueError:
        whole = None
    if _text_blocks(whole):
        # a tool result the harness stored as a file: the answer is the text of its blocks, joined
        return candidates("".join(b["text"] for b in whole), key)
    if isinstance(whole, (dict, list)):
        if isinstance(whole, dict) and "message" not in whole:
            return [unwrap(whole, key)]
        if isinstance(whole, list):
            return [whole]
    texts = _assistant_texts(text.splitlines())
    if texts is not None:
        return [unwrap(v, key) for t in texts for v in values_in(t)]
    return [unwrap(v, key) for v in values_in(text)]


def matches(value, key=None, want_list=False):
    if want_list and not isinstance(value, list):
        return False
    if not isinstance(value, (dict, list)):
        return False
    if key is None:
        return True
    if isinstance(value, dict):
        return key in value
    first = next((v for v in value if isinstance(v, dict)), None)
    return first is not None and key in first


def pick(text, key=None, want_list=False):
    """The last JSON value of `text` that matches, or None."""
    found = [v for v in candidates(text, key) if matches(v, key, want_list)]
    return found[-1] if found else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("src", help="workflow output, transcript (.jsonl) or text; - for standard input")
    ap.add_argument("dest", help="the JSON file to write")
    ap.add_argument("--key", help="take only an object (or a list of objects) that holds this key")
    ap.add_argument("--list", action="store_true", help="take only a list")
    args = ap.parse_args(argv)
    try:
        text = sys.stdin.read() if args.src == "-" else open(args.src, encoding="utf-8").read()
    except OSError as exc:
        die(f"cannot read {args.src}: {exc.strerror}")
    value = pick(text, args.key, args.list)
    if value is None:
        wanted = "a list" if args.list else "a JSON object or list"
        die(f"no {wanted}{f' with the key {args.key}' if args.key else ''} in {args.src}")
    folder = os.path.dirname(os.path.abspath(args.dest))
    os.makedirs(folder, exist_ok=True)
    with open(args.dest, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    size = f"{len(value)} item(s)" if isinstance(value, list) else f"keys {', '.join(list(value)[:6])}"
    print(f"Wrote {args.dest}: {'list' if isinstance(value, list) else 'object'}, {size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
