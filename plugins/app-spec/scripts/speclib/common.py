"""Paths, file walking, JSON, endpoint normalization, masking and read-only git for App Fusion.

Everything here treats the analyzed code as untrusted data: files are read, never executed, never written.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# Directories that hold generated, vendored or cached code. Never part of an inventory.
EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "Pods", "Carthage", "DerivedData", "build", "Build", ".build",
    ".gradle", ".idea", ".vscode", ".yarn", ".expo", ".next", "dist", "coverage", "__pycache__", ".swiftpm",
    "vendor", "bower_components", ".cxx", ".externalNativeBuild", "intermediates", "generated", ".dart_tool",
    "xcuserdata", ".bundle", "fastlane_output", "SourcePackages", "checkouts", ".cache", "tmp",
}

TEST_PATH = re.compile(
    r"(^|/)(__tests__|__mocks__|__fixtures__|tests?|Tests|[A-Za-z0-9_]+Tests|[A-Za-z0-9_]+UITests|androidTest|testFixtures|"
    r"e2e|fixtures|mocks?|Mocks|stories|storybook|TestUtils|TestResources|SnapshotTestUtils|Preview Content)(/|$)"
    r"|\.(test|spec|stories|e2e)\.[A-Za-z]+$|(^|/)msw[A-Za-z]*\.[jt]sx?$|Tests?\.swift$|Mock[A-Za-z0-9_]*\.swift$"
    r"|[A-Za-z0-9_]+(Test|Tests|Mock|Fake|Stub)\.(kt|java)$"
)

SOURCE_EXT = {
    ".swift", ".m", ".mm", ".h", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".kt", ".kts", ".java", ".dart",
    ".c", ".cc", ".cpp", ".cs", ".py", ".rb",
}

LANG_BY_EXT = {
    ".swift": "Swift", ".m": "Objective-C", ".mm": "Objective-C++", ".h": "C Header", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".kt": "Kotlin", ".kts": "Kotlin", ".java": "Java", ".dart": "Dart", ".c": "C", ".cc": "C++", ".cpp": "C++",
    ".cs": "C#", ".py": "Python", ".rb": "Ruby",
}

MAX_FILE_BYTES = 2_000_000


def die(message, code=2):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(code)


def check_name(value, what="name"):
    if not value or not SAFE_NAME.match(value):
        die(f"{what} {value!r} must be letters, digits, '-' or '_' (at most 64), starting with a letter or digit")
    return value


PLACEHOLDER = re.compile(r"^(?:_+|\.+|-+|<[^>]*>|tbd|todo|n/?a|none|nobody|unknown|user|me|you|test|anonymous|x+)$", re.I)
# words that make up the name of a model or an assistant; a name is refused only when EVERY word is one of these (or
# a version), so "Claude Dubois", "Ai Tanaka" and "Agent Smith" are people, while "Claude", "Claude Fable", "the
# assistant", "AI agent" and "gpt-5" are not
MODEL_WORDS = {"claude", "fable", "opus", "sonnet", "haiku", "mythos", "gpt", "chatgpt", "copilot", "gemini", "llama", "mistral",
               "assistant", "model", "agent", "bot", "ai", "llm", "anthropic", "openai", "code", "the", "an", "a", "user", "system",
               "coding", "language", "large"}


def person_name(value):
    """A person's name as they gave it, or None. Empty values, placeholders, the name of a model or an assistant, and
    control or shell punctuation are refused: a sign-off or a decision carries a person's own name, in any script."""
    who = one_line(value, 80)
    if not who or sum(1 for ch in who if ch.isalpha()) < 2:
        return None
    if re.search(r"[;&|<>`$\x00-\x1f]", who) or PLACEHOLDER.match(who):
        return None
    words = [w for w in re.split(r"[^\w]+", who.lower()) if w]
    if words and all(w in MODEL_WORDS or re.match(r"^v?\d[\w.]*$", w) for w in words):
        return None
    return who


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- json

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        print(f"warning: {path} could not be read as JSON ({exc.__class__.__name__}); treated as missing", file=sys.stderr)
        return default


_UMASK = os.umask(0)
os.umask(_UMASK)
FILE_MODE = 0o666 & ~_UMASK

# Languages that count as program code; data and prose formats (JSON, YAML, Markdown, XML ...) are listed but not summed.
PROGRAMMING = {"Swift", "Objective-C", "Objective-C++", "C Header", "TypeScript", "TypeScript Typings", "TSX", "JavaScript",
               "JSX", "Kotlin", "Java", "Dart", "C", "C++", "C#", "Python", "Ruby", "Go", "Rust", "Shell", "Groovy", "Scala",
               "Vue", "Svelte", "CSS", "SASS", "LESS", "Metal", "GraphQL"}


def write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.chmod(tmp, FILE_MODE)
    os.replace(tmp, path)


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".tmp-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, FILE_MODE)
    os.replace(tmp, path)


# ---------------------------------------------------------------- files

def walk(root, exts=None, include_tests=True):
    """Yield (relative path, absolute path) for files under root, skipping generated and vendored directories.

    Symlinked directories inside the tree are not followed, so a link can never pull a file from outside it.
    """
    root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS and not d.endswith((".xcassets", ".imageset", ".appiconset", ".lproj.bak")))
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if exts is not None and os.path.splitext(name)[1] not in exts:
                continue
            if not include_tests and is_test_path(rel):
                continue
            yield rel, full


def is_test_path(rel):
    return bool(TEST_PATH.search(rel))


def read_text(path, limit=MAX_FILE_BYTES):
    try:
        if os.path.getsize(path) > limit:
            return None
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", errors="replace")


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def match_brace(text, open_index, open_char="{", close_char="}"):
    """Index of the bracket closing the one at open_index, skipping string literals and comments. -1 if unbalanced."""
    depth = 0
    i = open_index
    n = len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in "\"'`":
            in_str = c
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
            continue
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        elif c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def strip_comments(text):
    """Blank out // and /* */ comments (keeping line numbers), leaving string literals alone."""
    out = []
    i, n = 0, len(text)
    in_str = None
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == in_str or (c == "\n" and in_str != "`"):
                in_str = None
            i += 1
            continue
        if c in "\"'`":
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            nl = text.find("\n", i)
            nl = n if nl < 0 else nl
            out.append(" " * (nl - i))
            i = nl
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            chunk = text[i:end]
            out.append("".join("\n" if ch == "\n" else " " for ch in chunk))
            i = end
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------- lines of code

def loc_by_language(root, include_tests=True):
    """Lines of code per language. Uses scc when installed (rule says which), else counts non-blank lines."""
    scc = shutil.which("scc")
    if scc:
        try:
            excl = ",".join(sorted(EXCLUDE_DIRS))
            out = subprocess.run(
                [scc, "--format", "json", "--no-cocomo", "--exclude-dir", excl, os.path.realpath(root)],
                capture_output=True, text=True, timeout=300, check=False,
            )
            data = json.loads(out.stdout or "[]")
            langs = [
                {"name": d.get("Name"), "files": d.get("Count", 0), "code": d.get("Code", 0),
                 "complexity": d.get("Complexity", 0)}
                for d in data if d.get("Code", 0) > 0
            ]
            langs.sort(key=lambda d: -d["code"])
            return langs, "scc: code lines per language, generated and vendored directories excluded"
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    counts = {}
    for rel, full in walk(root, SOURCE_EXT, include_tests=include_tests):
        text = read_text(full)
        if text is None:
            continue
        lang = LANG_BY_EXT.get(os.path.splitext(rel)[1], "Other")
        entry = counts.setdefault(lang, {"name": lang, "files": 0, "code": 0})
        entry["files"] += 1
        entry["code"] += sum(1 for line in text.splitlines() if line.strip())
    langs = sorted(counts.values(), key=lambda d: -d["code"])
    return langs, "non-blank lines per language (scc not installed), generated and vendored directories excluded"


# ---------------------------------------------------------------- endpoints

_HOST = re.compile(r"^[a-z][a-z0-9+.-]*://[^/]*", re.I)
_PARAM = re.compile(r"\$\{[^}]*\}|\\\([^)]*\)|\{[^}/]*\}|(?<=/):[A-Za-z_][A-Za-z0-9_]*|%[@dlfsu]|<[^>/]+>")


def _replace_templates(s):
    """Replace ${ ... } (with nested braces) and Swift \\( ... ) (with nested parentheses) by {}."""
    out, i, n = [], 0, len(s)
    while i < n:
        if s.startswith("${", i) or s.startswith("\\(", i):
            open_c, close_c = ("{", "}") if s[i] == "$" else ("(", ")")
            depth, j = 0, i + 1
            while j < n:
                if s[j] == open_c:
                    depth += 1
                elif s[j] == close_c:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("{}")
            i = j + 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def normalize_endpoint(raw):
    """Normalize a URL or path to a comparable form.

    Scheme and host are dropped, parameters of any syntax (${x}, \\(x), {x}, :x, %@, <x>) become {}, the query and
    fragment are dropped, duplicate slashes collapse, trailing slashes go, and the result is lowercase. Returns None
    for something that is not path-shaped.
    """
    if raw is None:
        return None
    s = str(raw).strip().strip("\"'`")
    s = _HOST.sub("", s)
    s = _replace_templates(s)
    s = _PARAM.sub("{}", s)
    s = re.split(r"[?#]", s, maxsplit=1)[0]
    s = re.sub(r"\{\}(\{\})+", "{}", s)
    s = s.strip()
    if not s or s.startswith("{}") and "/" not in s[2:]:
        return None
    if s.startswith("{}/"):
        s = s[2:]
    elif s.startswith("{}") and not s.startswith("{}/"):
        # a base-url placeholder glued to the path: ${base}users/{id}
        s = "/" + s[2:]
    if not s.startswith("/"):
        s = "/" + s
    s = re.sub(r"/{2,}", "/", s)
    s = s.rstrip("/") or "/"
    s = re.sub(r"(?<=[A-Za-z0-9_])\{\}$", "", s)  # a query-string builder glued to the last segment
    # concrete ids in recorded traffic or literals: numbers, UUIDs, long hex or base64-ish tokens become parameters
    s = "/".join("{}" if re.fullmatch(r"\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{24,}", seg)
                 else seg for seg in s.split("/"))
    s = s.lower()
    if s == "/" or not re.search(r"[a-z]", s):
        return None
    if " " in s or len(s) > 200:
        return None
    return s


_MIME = re.compile(r"^(application|text|image|audio|video|multipart|font|message|model)/[A-Za-z0-9.+*-]+$", re.I)
_FILEISH = re.compile(r"\.(png|jpe?g|gif|svg|pdf|json|plist|html?|css|js|ttf|otf|mp4|mov|wav|mp3|zip|txt|md|strings|xcstrings)$", re.I)


def looks_like_path(raw):
    """A literal that plausibly names an HTTP endpoint: has a '/', is not a MIME type, a date format, a file name, a
    local file path or a regular expression."""
    s = str(raw or "").strip()
    if "/" not in s or len(s) > 300 or "\n" in s:
        return False
    if _MIME.match(s) or re.match(r"^[dMyHhms]{1,4}([/.-][dMyHhms]{1,4})+$", s):
        return False
    if s.startswith(("file:", "data:", "mailto:", "tel:", "sms:", "./", "../", "~/", "#")):
        return False
    body = re.split(r"[?#]", s, maxsplit=1)[0]
    if _FILEISH.search(body) and not body.lower().endswith(".json") or re.search(r"[\\^$*+[\]]{2,}", s):
        return False
    return True


def endpoint_segments(path):
    return [seg for seg in path.strip("/").split("/") if seg]


def endpoints_match(a, b):
    """True when two normalized paths name the same endpoint: the shorter is a suffix of the longer at a segment
    boundary (covers base-URL prefix differences), '{}' matches any one segment, no two literal segments differ, and
    enough literals agree: at least min(2, literal segments of the shorter path), including the shorter path's last
    literal segment. So /users/{}/settings matches /api/users/{}/settings, but /financials/{}/{} does not match
    /employees/{}/calendar/checkin."""
    if not a or not b:
        return False
    sa, sb = endpoint_segments(a), endpoint_segments(b)
    if len(sa) > len(sb):
        sa, sb = sb, sa
    if not sa or (len(sa) < 2 and len(sa) != len(sb)):
        return False
    tail = sb[len(sb) - len(sa):]
    equal_literals = 0
    for x, y in zip(sa, tail):
        if x != "{}" and y != "{}":
            if x != y:
                return False
            equal_literals += 1
    literals = [i for i, x in enumerate(sa) if x != "{}"]
    if not literals:
        return sa == tail
    last = literals[-1]
    if tail[last] != sa[last]:
        return False
    return equal_literals >= min(2, len(literals))


# ---------------------------------------------------------------- secrets

_SECRETISH = re.compile(
    r"(?i)(api[_-]?key|secret|password|passwd|token|bearer|private[_-]?key|client[_-]?secret|sig=|signature)"
)


def mask(value, keep=3):
    s = str(value)
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "****"


def looks_secret(name_or_text):
    return bool(_SECRETISH.search(str(name_or_text)))


def sanitize_url(url):
    """Drop userinfo and credential-looking query parameters from a URL, so it can go into a shared artifact."""
    if not url:
        return url
    s = re.sub(r"^([a-z][a-z0-9+.-]*://)[^/@]+@", r"\1", str(url), flags=re.I)
    s = re.sub(r"(?i)([?&](?:[a-z_-]*token|[a-z_-]*key|[a-z_-]*secret|password|passwd|pwd|sig|signature|auth|code)=)[^&#]*",
               r"\1****", s)
    return s


# ---------------------------------------------------------------- git (read-only verbs only)

def git(path, *args, timeout=30):
    if not shutil.which("git"):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout, check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def git_info(path):
    """Commit, branch, remote (sanitized) and whether the working tree is clean. Never fetches, never writes."""
    real = os.path.realpath(path)
    if git(real, "rev-parse", "--is-inside-work-tree") != "true":
        return {"commit": None, "branch": None, "repo": None, "clean": None, "shallow": None}
    # untracked files count: a file an agent added is a change too (ignored files, such as build output, do not)
    status = git(real, "status", "--porcelain", "--untracked-files=normal")
    return {
        "commit": git(real, "rev-parse", "HEAD"),
        "branch": git(real, "rev-parse", "--abbrev-ref", "HEAD"),
        "repo": sanitize_url(git(real, "config", "--get", "remote.origin.url")),
        "clean": None if status is None else status == "",
        "shallow": git(real, "rev-parse", "--is-shallow-repository") == "true",
    }


# ---------------------------------------------------------------- text helpers for markdown output

def one_line(value, limit=240):
    text = " ".join(str("" if value is None else value).split())
    text = text.replace("|", "/")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(one_line(c, 400) for c in row) + " |")
    return "\n".join(out)
