#!/usr/bin/env python3
"""PreToolUse guard: app-spec never writes into the analysed app or into a backend contract repository.

Reads the hook input (JSON on stdin), from Claude Code or from Devin, which names its tools differently. It finds the
output folder(s) (a folder with app-spec.json) from the project folder, the shell's folder, the path a file tool writes
and the paths a shell command names, walking up, and down two levels below the project folder (the default output folder is ./specs/<name>), so it works when the agent was
started above or inside the output folder. Outside every output folder it does nothing. Each app-spec.json protects
app.path and every contracts[].path. Nothing inside the output folder is protected: the scripts write there.
  - a file write (Claude Code's Edit, Write, MultiEdit, NotebookEdit; Devin's edit, write, notebook_edit and every file
    an apply_patch adds, updates, deletes or moves to) whose path resolves under a protected root is denied; paths are
    compared without regard to case on macOS and Windows;
  - the shell is Claude Code's Bash, Devin's exec (in its workdir) and the text Devin's write_to_process types;
  - the shell is read the way a shell reads it: operators (; && || | &) and new lines split the command, shell
    keywords (do, then, if ...) are stepped over, `cd` and `pushd` move the folder for what follows, every redirect
    form (> >> >| 2> &> ...) names a target, `sh -c`, `bash -lc` and `eval` are read inside, a script a shell or an
    interpreter runs is read when it is a file outside this plugin, a script piped into a shell is "unsure",
    heredocs and inline code (python -c, python -, node -e ...) are scanned for the paths they open and whether they
    write or spawn a process, `xargs` takes the paths of the command before the pipe, `find -exec` is read for the
    command it runs, and `dd of=`, `curl -o`, `tar -C`, `sed -i`, `perl -pi`, package managers, build tools,
    formatters with --fix or --write, and git (with -C, --git-dir, --work-tree) name their targets;
  - a shell command that writes into a protected root is sent to the person to approve (ask): redirects, file writers,
    build tools and package managers run inside it, formatters, patch, inline code writing relative paths there, a
    git command that changes the repository, a recursive verb on a folder above it;
  - a write whose target the guard cannot resolve (a variable, a substitution, a brace expansion, a cd into an
    unknown folder, a script piped into a shell) is sent to the person when the command also names a protected
    root: unsure is asked, never silently allowed. Reads (cat, grep, git status/log/diff, copies out of the app)
    pass silently.
Set the plugin option guard=false (or APP_SPEC_GUARD=false where plugin options do not exist) to turn it off.
Standard library only, Python 3.8 or later.
"""

import glob
import json
import os
import re
import shlex
import sys

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "edit", "write", "notebook_edit"}  # Claude Code, Devin
PATCH_TOOLS = {"apply_patch"}
SHELL_TOOLS = {"Bash", "exec", "write_to_process"}
PATCH_FILE = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$", re.M)
WRITE_VERBS = {"rm", "rmdir", "mv", "cp", "tee", "touch", "truncate", "chmod", "chown", "ln", "mkdir", "install", "rsync",
               "unzip", "patch", "dd", "shred", "tar", "curl", "wget", "zip", "gunzip", "gzip", "ditto", "xattr", "bzip2", "xz"}
DEST_LAST = {"cp", "rsync", "install", "ln", "ditto"}
RECURSIVE = {"rm", "rmdir", "mv", "cp", "rsync", "install", "ln", "ditto", "tar", "unzip", "dd", "find", "chmod", "chown"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
SHELL_C = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
SHELL_KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "time", "coproc", "function", "["}
WRAPPERS = {"sudo", "doas", "env", "command", "nohup", "time", "nice", "exec", "caffeinate", "stdbuf", "builtin"}
INTERPRETERS = {"python", "python2", "python3", "node", "nodejs", "perl", "ruby", "osascript", "deno", "bun"}
INLINE_FLAGS = {"-c", "-e", "-E", "--eval", "-p", "--print"}
GIT_WRITES = {"commit", "checkout", "reset", "clean", "stash", "apply", "am", "merge", "rebase", "pull", "restore", "switch",
              "rm", "mv", "add", "cherry-pick", "revert", "tag", "branch", "worktree", "gc", "prune", "fetch", "init", "push",
              "update-ref", "symbolic-ref", "filter-branch", "submodule", "lfs", "notes", "replace", "sparse-checkout",
              "checkout-index", "read-tree", "write-tree", "update-index", "pack-refs", "reflog", "bisect", "remote", "config"}
GIT_READ_FORMS = {"branch": {"--show-current", "--list", "-l", "-a", "-r", "-v", "-vv", "--contains", "--merged", "--no-merged",
                             "--points-at", "--format"},
                  "tag": {"-l", "--list", "-n", "--contains", "--points-at", "--format"}, "stash": {"list", "show"},
                  "worktree": {"list"}, "fetch": {"--dry-run"}, "remote": {"-v", "show", "get-url"},
                  "submodule": {"status", "summary", "foreach"}, "lfs": {"ls-files", "status", "env", "version", "logs"},
                  "reflog": {"show"}, "notes": {"list", "show"}, "sparse-checkout": {"list"}, "bisect": {"log", "visualize", "view"},
                  "config": {"--get", "--list", "-l", "--get-all", "--get-regexp", "--show-origin", "--show-scope"}}
GIT_READ_WHEN_BARE = {"branch", "tag", "worktree", "remote", "reflog", "config", "lfs"}
PKG_VERBS = {"npm", "yarn", "pnpm", "bun"}
PKG_READS = {"ls", "list", "view", "info", "why", "outdated", "-v", "--version", "help", "--help", "-h", "test", "t", "jest", "audit",
             "explain", "licenses", "bin", "root", "prefix", "start", "config", "cache"}
PKG_RUN_READS = {"test", "lint", "typecheck", "tsc", "check", "start", "storybook"}
PKG_DIR_OPTS = {"--prefix", "--cwd", "-C", "--project-directory", "-p", "--project-dir", "--dir", "--filter"}
# build tools and formatters that write into the folder they run in: None = always, a set = when one of these appears
BUILD_WRITES = {"gradlew": None, "gradle": None, "carthage": None, "tuist": None, "make": None, "cmake": None, "fastlane": None,
                "swiftformat": None, "black": None, "isort": None, "patch": None,
                "swift": {"build", "test", "package", "run"}, "flutter": {"pub", "build", "test", "clean", "create", "gen-l10n", "run"},
                "dart": {"pub", "run", "compile", "format"}, "pod": {"install", "update", "deintegrate", "repo"},
                "bundle": {"install", "update", "exec"}, "swiftlint": {"--fix", "autocorrect"}, "eslint": {"--fix"},
                "prettier": {"--write", "-w"}, "rubocop": {"-a", "-A", "--autocorrect", "--auto-correct"}, "gofmt": {"-w"},
                "ktlint": {"-F", "--format"}, "biome": {"--write", "--fix"}}
XCODEBUILD_READS = {"-list", "-showsdks", "-version", "-showBuildSettings", "-showdestinations", "-usage", "-help"}

# code that writes files, or that spawns a process which may: a read (open(path), json.load, print) never matches
CODE_WRITES = re.compile(r"""open\s*\([^)]*['"](?:[wax]|r\+|[wa]b|[wa]\+)['"]|os\.open\s*\(|write_text|write_bytes|writeFile|appendFile|"""
                         r"""createWriteStream|os\.(?:remove|unlink|rename|replace|rmdir|makedirs|mkdir|truncate|"""
                         r"""chmod|link|symlink|system|popen)|shutil\.|subprocess|child_process|execSync|spawnSync|\bspawn\s*\(|"""
                         r"""\bunlink(?:Sync)?\s*\(|\brename(?:Sync)?\s*\(|\brmSync|\bmkdirSync|\bcopyFile|\bcpSync|\bwriteSync|"""
                         r"""\bopenSync|\btruncateSync|fs\.promises\.(?:write|unlink|rename|rm|mkdir|copy)|\.unlink\(\)|\.touch\(\)|"""
                         r""">\s*[\w./$]|\bFile\.(?:write|delete|open)|\bFileUtils|\bIO\.write""")
SHELL_WRITES = re.compile(r"\b(?:rm|mv|cp|tee|dd|truncate|install|rsync|ditto|touch|mkdir|patch)\b|>\s*\S|\bsed\s+-i|\bperl\s+-p?i")
PATHISH = re.compile(r"(?:~|\$\w+|\$\(pwd\)|\.{1,2})?/?(?:[\w.$@{}-]+/)+[\w./${}@-]*|/[\w./${}@-]{2,}")
CAT_SUBST = re.compile(r"\$\(\s*cat\s+([^\s)]+)\s*\)|`\s*cat\s+([^\s`]+)\s*`")
REDIRECT = re.compile(r"^(?:\d*>>?\|?|&>>?|\d*<>)$")
DUP = re.compile(r"^(?:\d*>&|\d*<&|>&\d*|<&\d*)$")
OPERATORS = {";", ";;", "&&", "||", "|", "|&", "&", "(", ")", "{", "}", "\n"}
CASE_FOLD = sys.platform in ("darwin", "win32")
MAX_DEPTH = 3
MAX_GLOB = 200
MAX_SCRIPT = 262_144
PLUGIN_ROOT = os.path.realpath(os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("DEVIN_PLUGIN_ROOT")
                               or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fold(path):
    return path.lower() if CASE_FOLD else path


def under(path, root):
    p, r = fold(path), fold(root)
    return p == r or p.startswith(r + os.sep)


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


# ---------------------------------------------------------------- paths

def resolve(path, cwd):
    """Absolute, symlink-resolved form of a path that may not exist yet (resolve the deepest existing ancestor)."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    p = os.path.normpath(p)
    head, tail = p, []
    while head and not os.path.exists(head):
        head, part = os.path.split(head)
        tail.insert(0, part)
        if head == os.path.dirname(head):
            break
    real = os.path.realpath(head) if head else head
    return os.path.normpath(os.path.join(real, *tail)) if tail else real


def literal(token):
    """False when the shell would still change the token: a variable, a substitution, a brace expansion."""
    return not re.search(r"\$|`|\{[^}]*\}", token)


def targets_of(token, cwd):
    """(resolved paths a token names, whether it was literal). A glob is expanded against cwd."""
    if not literal(token):
        return [], False
    if re.search(r"[*?\[]", token):
        pattern = os.path.expanduser(token)
        if not os.path.isabs(pattern):
            pattern = os.path.join(cwd, pattern)
        matches = glob.glob(pattern)[:MAX_GLOB]
        return [resolve(m, cwd) for m in matches] or [resolve(re.split(r"[*?\[]", token)[0] or ".", cwd)], True
    return [resolve(token, cwd)], True


def repo_top(path):
    """The git repository a folder belongs to (the nearest folder with a .git entry), or None."""
    d = os.path.realpath(path)
    for _ in range(64):
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


# ---------------------------------------------------------------- the output folder(s)

CONFIG = "app-spec.json"


def load_config(folder):
    """The parsed app-spec.json of a folder, or None when there is none or it is not an object."""
    try:
        with open(os.path.join(folder, CONFIG), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def protected_roots(cfg, base=None):
    """The real paths app-spec never writes under: app.path and every contracts[].path of a configuration.
    A relative path is read against `base` (the output folder) when one is given."""
    paths = []
    app = cfg.get("app") if isinstance(cfg, dict) else None
    if isinstance(app, dict) and isinstance(app.get("path"), str) and app["path"]:
        paths.append(app["path"])
    contracts = cfg.get("contracts") if isinstance(cfg, dict) else None
    for entry in contracts if isinstance(contracts, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]:
            paths.append(entry["path"])
    roots = []
    for p in paths:
        full = os.path.expanduser(p)
        if base and not os.path.isabs(full):
            full = os.path.join(base, full)
        real = os.path.realpath(full)
        if real not in roots:
            roots.append(real)
    return roots


def find_outputs(candidates, below):
    """Every folder with app-spec.json at or above a candidate path, or one or two levels below the `below` folders."""
    found = []

    def add(folder):
        real = os.path.realpath(folder)
        if real not in found and os.path.isfile(os.path.join(real, CONFIG)):
            found.append(real)

    for c in candidates:
        if not c:
            continue
        # the path as written and the path its links point to: a link into the app leads outside the output folder
        for variant in dict.fromkeys([os.path.normpath(c), os.path.realpath(c)]):
            d = variant if os.path.isdir(variant) else os.path.dirname(variant)
            seen = 0
            while d and seen < 64:
                add(d)
                parent = os.path.dirname(d)
                if parent == d:
                    break
                d, seen = parent, seen + 1
    # The default output folder is ./specs/<name>, two levels down. A child named specs is scanned first, each child
    # has its own cap, and a total ceiling keeps a huge project fast, so one large folder cannot starve the scan.
    ceiling = 4000
    for c in [x for x in below if x]:
        try:
            children = os.listdir(c)
        except OSError:
            continue
        children = sorted(children, key=lambda n: (n != "specs", n))[:400]
        for n in children:
            child = os.path.join(c, n)
            if not os.path.isdir(child):
                continue
            add(child)
            if n.startswith(".") or n == "node_modules" or ceiling <= 0:
                continue
            try:
                grandchildren = sorted(os.listdir(child))[:400]
            except OSError:
                continue
            ceiling -= len(grandchildren)
            for g in grandchildren:
                if os.path.isdir(os.path.join(child, g)):
                    add(os.path.join(child, g))
    return found


class Protected:
    """The source app and contract repository roots of every output folder found."""

    def __init__(self, outputs):
        self.roots = []  # real paths
        self.outputs = []  # output folders, whose own files are never protected
        for out in outputs:
            cfg = load_config(out)
            self.outputs.append(out)
            for root in protected_roots(cfg, out) if cfg else []:
                if root not in self.roots:
                    self.roots.append(root)
        # an output folder that lies inside the app is still where the spec is written
        self.free = [o for o in self.outputs if not any(under(r, o) for r in self.roots)]

    def root_of(self, path):
        """The protected root a resolved path lies under, or None."""
        if any(under(path, o) for o in self.free):
            return None
        for root in self.roots:
            if under(path, root):
                return root
        return None

    def holds(self, path):
        """The protected root that lies below a folder (a recursive verb on the folder reaches it), or None."""
        for root in self.roots:
            if under(root, path) and fold(root) != fold(path):
                return root
        return None

    def mentions(self, text):
        """True when the text names a protected root."""
        return any(fold(root) in fold(text) for root in self.roots)

# ---------------------------------------------------------------- reading a shell command

def tokenize(command):
    command = command.replace("\r\n", "\n").replace("\n", " ; ")  # a new line starts a new command, like ;
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return command.split()


def segments(tokens):
    """[(argv, operator before it)] split on shell operators."""
    segs, cur, op = [], [], None
    for t in tokens:
        if t in OPERATORS:
            if cur:
                segs.append((cur, op))
                cur = []
            op = t
        else:
            cur.append(t)
    if cur:
        segs.append((cur, op))
    return segs


def split_redirects(argv):
    """(arguments, output targets, input files, heredoc?): redirect operators and their targets taken out."""
    args, targets, inputs, heredoc = [], [], [], False
    i = 0
    while i < len(argv):
        t = argv[i]
        if t in ("<<", "<<-", "<<<"):
            heredoc = heredoc or t != "<<<"
            i += 2
            continue
        if DUP.match(t):
            i += 2 if t.endswith("&") else 1
            continue
        if REDIRECT.match(t) and i + 1 < len(argv):
            target = argv[i + 1]
            if not target.startswith("&") and target not in ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"):
                targets.append(target)
            i += 2
            continue
        if t == "<" and i + 1 < len(argv):  # input redirect: a read, but a shell may run what it reads
            inputs.append(argv[i + 1])
            i += 2
            continue
        if re.match(r"^\d+$", t) and i + 1 < len(argv) and (REDIRECT.match(argv[i + 1]) or DUP.match(argv[i + 1])):
            i += 1  # the fd number before an operator
            continue
        args.append(t)
        i += 1
    return args, targets, inputs, heredoc


def strip_wrappers(argv):
    while argv:
        head = os.path.basename(argv[0])
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]) or head in SHELL_KEYWORDS:
            argv = argv[1:]
        elif head in WRAPPERS:
            argv = argv[1:]
            while argv and argv[0].startswith("-") and head in ("env", "sudo", "nice", "nohup", "stdbuf", "time"):
                argv = argv[1:]
        else:
            break
    return argv


class Findings:
    def __init__(self):
        self.deny, self.ask, self.unsure = [], [], []

    def add(self, kind, reason):
        getattr(self, kind).append(reason)


def classify_write(prot, path, what, f, recursive=False):
    """A shell write to a resolved path: ask for a protected root (or a folder above one, for a recursive verb)."""
    root = prot.root_of(path)
    if root:
        f.add("ask", f"{what} {root}: app-spec never edits the source app or a contract repository")
        return True
    if recursive:
        held = prot.holds(path)
        if held:
            f.add("ask", f"{what} a folder above {held}: app-spec never edits the source app or a contract repository")
            return True
    return False


def scan_code(code, cwd, prot, f, label, shell=False):
    """Inline code, a heredoc body or a script file: the paths it names, and whether it writes or spawns."""
    writes = bool(CODE_WRITES.search(code)) or (shell and bool(SHELL_WRITES.search(code)))
    hits = False
    for m in PATHISH.finditer(code):
        frag = m.group(0).strip("'\"")
        if not frag or frag in ("/", "//"):
            continue
        paths, lit = targets_of(frag, cwd)
        if not lit:
            if writes:
                f.add("unsure", f"{label} names {frag}, which the guard cannot resolve, and writes files")
            continue
        for p in paths:
            if writes:
                hits = classify_write(prot, p, f"{label} writes", f, recursive=True) or hits
    if writes and not hits:
        # relative paths: the code writes where the shell stands
        root = prot.root_of(cwd)
        if root:
            f.add("ask", f"{label} writes files while the shell is in {root}")
    return hits


def scan_script(token, cwd, prot, f, label):
    """A script file a shell or an interpreter is about to run: read it, unless it is this plugin's own."""
    paths, lit = targets_of(token, cwd)
    if not lit:
        f.add("unsure", f"{label} runs a script whose path the guard cannot resolve")
        return
    for p in paths:
        if under(p, PLUGIN_ROOT) or not os.path.isfile(p):
            continue
        try:
            if os.path.getsize(p) > MAX_SCRIPT:
                f.add("unsure", f"{label} runs a large script the guard did not read ({os.path.basename(p)})")
                continue
            with open(p, encoding="utf-8", errors="replace") as fh:
                code = fh.read()
        except OSError:
            continue
        scan_code(code, cwd, prot, f, f"{label} (script {os.path.basename(p)})", shell=True)


def git_repo_and_sub(argv):
    """(the repository path option, the subcommand, its arguments) of a git command."""
    repo, i = None, 1
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a in ("-C", "--git-dir", "--work-tree") and i + 1 < len(argv):
            repo, i = argv[i + 1], i + 2
        elif a.startswith("--git-dir=") or a.startswith("--work-tree="):
            repo, i = a.split("=", 1)[1], i + 1
        elif a == "-c" and i + 1 < len(argv):
            i += 2
        else:
            i += 1
    sub = argv[i] if i < len(argv) else None
    return repo, sub, argv[i + 1:] if sub else []


def git_reads(sub, rest):
    """True for the read-only forms of a git write command."""
    if sub in GIT_READ_FORMS and any(a in GIT_READ_FORMS[sub] for a in rest):
        return True
    if sub in GIT_READ_WHEN_BARE and not rest:
        return True
    if sub == "stash" and rest and rest[0] in GIT_READ_FORMS["stash"]:
        return True
    if sub == "config":  # `git config user.name` reads; a value, --unset, --add or --edit writes
        positional = [a for a in rest if not a.startswith("-")]
        return len(positional) < 2 and not any(a in ("--unset", "--unset-all", "--add", "--replace-all", "--edit", "-e", "--rename-section",
                                                     "--remove-section") for a in rest)
    return False


def tool_dir(args, cwd):
    """The folder a package manager or build tool works in: an option's value, else the shell's folder."""
    for i, a in enumerate(args[:-1]):
        if a in PKG_DIR_OPTS:
            paths, lit = targets_of(args[i + 1], cwd)
            return paths[0] if lit and paths else None
    for a in args:
        if any(a.startswith(o + "=") for o in PKG_DIR_OPTS):
            paths, lit = targets_of(a.split("=", 1)[1], cwd)
            return paths[0] if lit and paths else None
    return cwd


def build_writes(verb, args):
    """True when a package manager, build tool or formatter would write into its folder."""
    rest = args[1:]
    if verb in PKG_VERBS:
        sub = next((a for a in rest if not a.startswith("-")), None)
        if sub is None:
            return not any(a in ("-v", "--version", "-h", "--help") for a in rest)  # bare `yarn` installs
        if sub == "run":
            script = next((a for a in rest[rest.index("run") + 1:] if not a.startswith("-")), None)
            return script not in PKG_RUN_READS
        return sub not in PKG_READS
    if verb == "npx":
        tool = next((a for a in rest if not a.startswith("-")), None)
        return bool(tool) and tool in BUILD_WRITES and build_writes(tool, args[args.index(tool):])
    if verb == "xcodebuild":
        return not any(a in XCODEBUILD_READS for a in rest)
    if verb in BUILD_WRITES:
        spec = BUILD_WRITES[verb]
        return spec is None or any(a in spec for a in rest)
    return False


def check_segment(argv, op, cwd, prot, f, prev_paths, depth, raw):
    """One simple command. Returns (new cwd or None when it cannot be known, the protected paths it mentioned)."""
    args, redirects, inputs, heredoc = split_redirects(argv)
    args = strip_wrappers(args)
    verb = os.path.basename(args[0]) if args else ""
    mentioned = []
    for tgt in redirects:
        paths, lit = targets_of(tgt, cwd)
        if not lit:
            f.add("unsure", f"redirects output into {tgt}, which the guard cannot resolve")
        for p in paths:
            classify_write(prot, p, "the command redirects output into", f)
    if verb in ("cd", "pushd"):
        target = args[1] if len(args) > 1 else os.path.expanduser("~")
        if target == "-":
            return None, mentioned
        paths, lit = targets_of(target, cwd)
        return (paths[0] if lit and paths and os.path.isdir(paths[0]) else None), mentioned
    # what this segment names, for xargs and for the unsure rule
    for a in args[1:]:
        if "/" in a or a.endswith(".json") or a.endswith(".md"):
            paths, lit = targets_of(a.split("=", 1)[1] if re.match(r"^--?[\w-]+=", a) else a, cwd)
            mentioned += [p for p in paths if prot.root_of(p)]
    if verb in SHELLS:
        if depth >= MAX_DEPTH:
            f.add("unsure", "nests shells deeper than the guard reads")
            return cwd, mentioned
        flag = next((a for a in args[1:4] if SHELL_C.match(a)), None)
        if flag:
            at = args.index(flag)
            inner = args[at + 1] if at + 1 < len(args) else ""
            for m in CAT_SUBST.finditer(inner):
                scan_script(m.group(1) or m.group(2), cwd, prot, f, f"`{verb} -c`")
            if not literal(inner):
                f.add("unsure", f"`{verb} -c` runs code the guard cannot read")
            check_command(inner, cwd, prot, f, depth + 1)
        else:
            script = next((a for a in args[1:] if not a.startswith("-")), None)
            if script:
                scan_script(script, cwd, prot, f, f"`{verb}`")
            if op in ("|", "|&") or "-s" in args[1:] or not script and not inputs:
                f.add("unsure", f"`{verb}` runs the commands piped into it")
            for src in inputs:
                scan_script(src, cwd, prot, f, f"`{verb}`")
        return cwd, mentioned
    if verb in ("source", "."):
        if len(args) > 1:
            scan_script(args[1], cwd, prot, f, "`source`")
        return cwd, mentioned
    if verb == "eval":
        if depth >= MAX_DEPTH:
            f.add("unsure", "nests shells deeper than the guard reads")
        else:
            inner = " ".join(args[1:])
            if not literal(inner):
                f.add("unsure", "`eval` runs code the guard cannot read")
            check_command(inner, cwd, prot, f, depth + 1)
        return cwd, mentioned
    if verb in ("perl", "ruby") and any(a.startswith("-pi") or a.startswith("-i") for a in args[1:4]):
        positional = [x for x in args[1:] if not x.startswith("-")]
        for a in positional[1:] if "-e" in args[1:4] or "-E" in args[1:4] else positional:
            paths, lit = targets_of(a, cwd)
            if not lit:
                f.add("unsure", f"an in-place edit changes {a}, which the guard cannot resolve")
            for p in paths:
                classify_write(prot, p, "an in-place edit would change", f)
        return cwd, mentioned
    if verb in INTERPRETERS or re.match(r"^python\d(\.\d+)?$", verb):
        flags = [a for a in args[1:4] if a in INLINE_FLAGS]
        stdin = "-" in args[1:3] or (heredoc and not any(not a.startswith("-") for a in args[1:2]))
        if flags or stdin or heredoc or (inputs and len(args) == 1):
            code = ""
            if flags:
                at = args.index(flags[0])
                code = " ".join(args[at + 1:])
            if heredoc or stdin:
                code += "\n" + (raw.split("\n", 1)[1] if "\n" in raw else "")
            scan_code(code, cwd, prot, f, f"inline {verb} code")
            for src in inputs:
                scan_script(src, cwd, prot, f, f"`{verb}`")
            return cwd, mentioned
        if "-m" not in args[:3] and len(args) > 1 and not args[1].startswith("-"):
            scan_script(args[1], cwd, prot, f, f"`{verb}`")
        return cwd, mentioned
    if verb == "git":
        repo, sub, rest = git_repo_and_sub(args)
        if sub in GIT_WRITES and not git_reads(sub, rest):
            where = resolve(repo, cwd) if repo else cwd
            root = prot.root_of(where)
            if root:
                f.add("ask", f"`git {sub}` would change the repository in {root} (fetching or committing writes its refs)")
            else:
                # an output folder inside the app (or a repository above it): the repository still holds the app
                top = repo_top(where)
                held = top and (prot.root_of(top) or prot.holds(top))
                if held:
                    f.add("ask", f"`git {sub}` in the repository {top} would change {held}: app-spec never edits the source app or a "
                                 "contract repository")
        return cwd, mentioned
    if verb == "find":
        options_at = next((k for k, a in enumerate(args[1:]) if a.startswith("-")), len(args) - 1)
        paths = args[1:1 + options_at]
        execs = [os.path.basename(args[i + 1]) for i, a in enumerate(args[:-1]) if a in ("-exec", "-execdir", "-ok", "-okdir")]
        writing = "-delete" in args or any(e in WRITE_VERBS or e in SHELLS or e in INTERPRETERS or e in ("sed", "perl", "git", "xargs")
                                           for e in execs)
        if writing:
            for a in paths or ["."]:
                for p in targets_of(a, cwd)[0]:
                    classify_write(prot, p, "`find` would change files under", f, recursive=True)
        return cwd, mentioned
    if verb == "xargs":
        inner = strip_wrappers([a for a in args[1:] if not a.startswith("-")])
        if inner and (os.path.basename(inner[0]) in WRITE_VERBS or os.path.basename(inner[0]) in ("sed", "perl", "git")):
            for p in prev_paths:
                classify_write(prot, p, f"`xargs {os.path.basename(inner[0])}` would change", f, recursive=True)
            if not prev_paths and op in ("|", "|&"):
                f.add("unsure", f"`xargs {os.path.basename(inner[0])}` changes whatever the pipe lists")
        return cwd, mentioned
    if verb == "sed" and any(a.startswith("-i") or a.startswith("--in-place") for a in args[1:5]):
        files = [a for a in args[1:] if not a.startswith("-")]
        if not any(a in ("-e", "-f") for a in args) and files:
            files = files[1:]  # the first non-option argument is the script
        for a in files:
            paths, lit = targets_of(a, cwd)
            if not lit:
                f.add("unsure", f"`sed -i` edits {a}, which the guard cannot resolve")
            for p in paths:
                classify_write(prot, p, "`sed -i` would edit", f)
        return cwd, mentioned
    if verb in PKG_VERBS or verb == "npx" or verb == "xcodebuild" or verb in BUILD_WRITES:
        if build_writes(verb, args):
            where = tool_dir(args, cwd)
            if where is None:
                f.add("unsure", f"`{verb}` works in a folder the guard cannot resolve")
            else:
                root = prot.root_of(where)
                if root:
                    f.add("ask", f"`{verb}` would write into {root} (build output, dependencies, lock files or formatted sources)")
        if verb != "patch":
            return cwd, mentioned
    if verb in WRITE_VERBS:
        targets = write_targets(verb, args, cwd)
        for a in targets:
            paths, lit = targets_of(a, cwd)
            if not lit:
                f.add("unsure", f"`{verb}` writes {a}, which the guard cannot resolve")
            for p in paths:
                classify_write(prot, p, f"`{verb}` would change", f, recursive=verb in RECURSIVE)
        return cwd, mentioned
    return cwd, mentioned


def write_targets(verb, args, cwd):
    """The arguments a writing command changes."""
    rest = args[1:]
    if verb == "dd":
        return [a.split("=", 1)[1] for a in rest if a.startswith("of=")]
    if verb == "curl":
        out = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-o", "--output", "--output-dir")]
        return out + (["."] if any(a in ("-O", "--remote-name") for a in rest) else [])
    if verb == "wget":
        out = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-O", "-P", "--output-document", "--directory-prefix")]
        return out or ["."]
    if verb == "tar":
        flags = "".join(a for a in rest if re.match(r"^-?[a-zA-Z]+$", a))
        dirs = [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-C", "--directory")] + \
               [a.split("=", 1)[1] for a in rest if a.startswith("--directory=")]
        if "x" in flags or "--extract" in rest:
            return dirs or ["."]
        if any(c in flags for c in "cru") or any(a in rest for a in ("--create", "--append", "--update")):
            return [rest[i + 1] for i, a in enumerate(rest[:-1]) if a in ("-f", "--file")] + [a.split("=", 1)[1] for a in rest if a.startswith("--file=")]
        return []
    if verb == "unzip":
        return [rest[i + 1] for i, a in enumerate(rest[:-1]) if a == "-d"] or ["."]
    positional = [a for a in rest if not a.startswith("-")]
    if verb == "zip":
        return positional[:1]  # the archive; what follows is read
    if verb == "patch":
        return positional or ["."]
    if verb == "xattr":
        return positional[1:] if any(a in ("-w", "-d", "-c") for a in rest) else []
    if verb in DEST_LAST:
        return positional[-1:]
    if verb == "mv":
        return positional  # moving a protected folder away changes it too
    return positional


def check_command(command, cwd, prot, f, depth=0):
    """Every segment of a shell command, with cd tracked and pipes remembered for xargs."""
    tokens = tokenize(command)
    cur = cwd
    prev_paths = []
    for argv, op in segments(tokens):
        new_cwd, mentioned = check_segment(argv, op, cur, prot, f, prev_paths if op in ("|", "|&") else [], depth, command)
        if new_cwd is None:  # a `cd` whose target the guard cannot resolve: what follows runs somewhere unknown
            f.add("unsure", "changes into a folder the guard cannot resolve")
        else:
            cur = new_cwd
        prev_paths = mentioned


# ---------------------------------------------------------------- main

def shell_input(tool, args):
    """The shell text of a call: Bash's and exec's command, or what write_to_process types (its keys as new lines)."""
    if tool == "write_to_process":
        text = args.get("text_input") or args.get("bytes_input")
        return re.sub(r"<(?:CR|LF)>", "\n", text) if isinstance(text, str) else None
    command = args.get("command")
    return command if isinstance(command, str) else None


def main():
    guard = os.environ.get("CLAUDE_PLUGIN_OPTION_GUARD") or os.environ.get("APP_SPEC_GUARD") or "true"
    if guard.strip().lower() in ("false", "0", "off", "no"):
        return
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(data, dict):
        return
    tool = data.get("tool_name")
    args = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    project = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("DEVIN_PROJECT_DIR") or ""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) and data.get("cwd") else (project or os.getcwd())
    if tool == "exec" and isinstance(args.get("workdir"), str) and args["workdir"]:
        cwd = os.path.join(cwd, os.path.expanduser(args["workdir"]))  # Devin's exec runs where workdir says
    candidates = [project or cwd, cwd]
    lexical = lambda p: os.path.normpath(os.path.join(cwd, os.path.expanduser(p)))
    targets, command = [], None
    if tool in WRITE_TOOLS:
        target = args.get("file_path") or args.get("notebook_path") or args.get("path")
        targets = [target] if isinstance(target, str) and target else []
    elif tool in PATCH_TOOLS:
        targets = PATCH_FILE.findall("\n".join(v for v in args.values() if isinstance(v, str)))
    elif tool in SHELL_TOOLS:
        command = shell_input(tool, args)
    if not targets and command is None:
        return
    candidates += [lexical(t) for t in targets]
    if command:
        for t in tokenize(command)[:60]:
            if "/" in t and literal(t) and not re.search(r"[*?\[]", t):
                candidates.append(lexical(t.split("=", 1)[1] if re.match(r"^--?[\w-]+=", t) else t))
    outputs = find_outputs(candidates, [project or cwd])
    if not outputs:
        return
    prot = Protected(outputs)
    for target in targets:
        full = resolve(target, cwd)
        root = prot.root_of(full)
        if root:
            decide("deny", f"app-spec never edits the source app: {target} is inside {root}, which an app-spec.json lists as the "
                           "analysed app or a contract repository. Write the spec under the output folder instead. (To change "
                           "that code on purpose, do it outside this session or set the plugin option guard=false, "
                           "APP_SPEC_GUARD=false outside Claude Code.)")
    if command is None:
        return
    f = Findings()
    check_command(command, cwd, prot, f)
    if f.ask:
        decide("ask", f"app-spec guard: {f.ask[0]}. Approve only if a person really wants this change.")
    if f.unsure and prot.mentions(command):
        decide("ask", f"app-spec guard: this command {f.unsure[0]}, and it names the source app or a contract repository. "
                      "The guard cannot tell where it writes: approve only if you can.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # a guard bug must never block the session; the permission rules still apply
        sys.exit(0)
