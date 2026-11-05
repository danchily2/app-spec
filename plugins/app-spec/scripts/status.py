#!/usr/bin/env python3
"""Where does the run stand, what is stale, and what is the exact next command?

    python3 status.py <out> [--json]

Reads the output folder `<out>` and its modification times; writes nothing. One line per stage, the staleness lines,
then `Next:`. `--json` prints the report as JSON. Exit code 0 always, 2 when `<out>` is not an output folder: a path
that is not a folder, or a folder that holds files but no `app-spec.json` and none of the files a run writes. An empty
or missing folder is a run that has not started: the next command is module.py.
Standard library only.
"""

import json
import os
import shlex
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from speclib import out, spec_md  # noqa: E402
from speclib.builder import evidence_name  # noqa: E402
from speclib.common import die  # noqa: E402
from speclib.template import APPENDICES  # noqa: E402

TOLERANCE = 1.0                      # seconds: file systems round times, and two writes of one run land together
CATALOGS = ("use-cases.json", "screens.json", "flows.json", "rules.json", "endpoints.json")
RESULTS = ("understand_result.json", "rules_result.json")
STAGES = ("module", "inventory", "understand", "rules", "contracts", "catalogs", "spec", "review", "tests", "compare")
# Files that mark a folder as an output folder even before `app-spec.json` exists.
KNOWN = {"app-spec.json", "module.json", "inventory.json", "fields.json", "ids.json", "overrides.json", "ledger.json",
         "grade.json", "review.json", "prose.json", *RESULTS, *CATALOGS}
DEFAULT_SPEC = "SPEC.md"


def script(name):
    """The command that runs one of the plugin's scripts from any folder."""
    return f'python3 "${{CLAUDE_PLUGIN_ROOT}}/scripts/{name}"'


def _mtime(dest, name):
    try:
        return os.path.getmtime(os.path.join(dest, name))
    except OSError:
        return None


def _newer(a, b):
    """True when time `a` is later than time `b` by more than the tolerance. A missing time is never newer."""
    return a is not None and b is not None and a > b + TOLERANCE


def _newest(dest, names):
    times = [t for t in (_mtime(dest, n) for n in names) if t is not None]
    return max(times) if times else None


def _oldest(dest, names):
    times = [t for t in (_mtime(dest, n) for n in names) if t is not None]
    return min(times) if times else None


def _check_folder(dest):
    if os.path.exists(dest) and not os.path.isdir(dest):
        die(f"{dest} is not an app-spec output folder (it is not a folder)")
    if os.path.isdir(dest) and os.listdir(dest) and not (KNOWN & set(os.listdir(dest))):
        die(f"{dest} is not an app-spec output folder (no app-spec.json and none of the files a run writes)")


def _config(dest):
    """The run configuration, or an empty dict when the run has not started or the file is unusable."""
    cfg = out.load(dest, out.CONFIG, {})
    return cfg if isinstance(cfg, dict) else {}


def _spec_name(cfg):
    options = cfg.get("options")
    name = options.get("specName") if isinstance(options, dict) else None
    return name if isinstance(name, str) and name else DEFAULT_SPEC


def _contracts_done(dest, cfg):
    """Done when no contract repository is configured, else when `contractsRun` of endpoints.json names every one.
    contracts.py records each repository it read there, whether or not a route matched."""
    configured = [c for c in cfg.get("contracts") or [] if isinstance(c, dict)]
    if not configured:
        return True
    doc = out.load(dest, "endpoints.json", {})
    runs = (doc.get("contractsRun") if isinstance(doc, dict) else None) or []
    read = {str(r.get("repo")) for r in runs if isinstance(r, dict) and r.get("repo")}
    names = {str(c.get("name") or os.path.basename(str(c.get("path") or "").rstrip(os.sep))) for c in configured}
    return names <= read


def _stages(dest, cfg, spec_name):
    files = {
        "module": ["module.json"], "inventory": ["inventory.json", "fields.json"],
        "understand": ["understand_result.json"], "rules": ["rules_result.json"], "contracts": ["endpoints.json"],
        "catalogs": list(CATALOGS), "spec": [spec_name], "review": ["review.json", "REVIEW.md"],
    }
    present = {
        "module": os.path.isfile(os.path.join(dest, "module.json")),
        "inventory": os.path.isfile(os.path.join(dest, "inventory.json")),
        "understand": os.path.isfile(os.path.join(dest, "understand_result.json")),
        "rules": os.path.isfile(os.path.join(dest, "rules_result.json")),
        "contracts": _contracts_done(dest, cfg),
        "catalogs": os.path.isfile(os.path.join(dest, "use-cases.json")),
        "spec": os.path.isfile(os.path.join(dest, spec_name)),
        "review": os.path.isfile(os.path.join(dest, "review.json")),
    }
    stages = {}
    for name in STAGES:
        names = files.get(name, [])
        done = present.get(name, False)
        stages[name] = {"status": "done" if done else "-", "mtime": _newest(dest, names) if done else None,
                        "files": names}
    return stages


def _appendix_f(text):
    """The lines of Appendix F in a spec's text, without blank lines at either end."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line.rstrip() == APPENDICES[5]
            continue
        if inside:
            lines.append(line)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _coverage_differs(dest, spec_name):
    """True when the spec's Appendix F is not what `render.py spec` would write from the current ledger.json. Content,
    not time: the review command runs ledger.py after the spec, and the same numbers must not stale the spec."""
    try:
        with open(os.path.join(dest, evidence_name(spec_name)), encoding="utf-8") as fh:  # the builder spec has no coverage
            written = _appendix_f(fh.read())
        want = spec_md.coverage(spec_md.Context(dest))
    except (OSError, UnicodeDecodeError, SystemExit, KeyError, TypeError, ValueError, AttributeError):
        return False  # a missing catalog or a broken file is reported by its own stage
    while want and not want[-1].strip():
        want = want[:-1]
    return written != want


def _stale(dest, spec_name):
    """What is out of date, in pipeline order. Each review pass runs the ledger, then the spec (its Appendix F reads
    ledger.json), then the grader (it reads the spec): the ledger is compared with what it reads, never the spec."""
    lines = []
    builder_t = _mtime(dest, spec_name)
    evidence_t = _mtime(dest, evidence_name(spec_name))
    # The spec is two files: compare with the older, so a half-refreshed pair is stale.
    spec_t = min(builder_t, evidence_t) if builder_t is not None and evidence_t is not None else builder_t
    if _newer(_mtime(dest, "module.json"), _mtime(dest, "inventory.json")) and os.path.isfile(os.path.join(dest, "inventory.json")):
        lines.append("the inventory predates module.json: re-run inventory.py")
    catalogs_t = _oldest(dest, CATALOGS)
    for name in RESULTS:
        if _newer(_mtime(dest, name), catalogs_t):
            lines.append(f"the catalogs predate {name}: re-run render.py catalogs")
    ledger_t = _mtime(dest, "ledger.json")
    for name in (*CATALOGS, "overrides.json"):
        if _newer(_mtime(dest, name), ledger_t):
            lines.append(f"the ledger predates {name}: run ledger.py")
    if builder_t is not None and evidence_t is None:
        lines.append("the spec predates the evidence split: re-run render.py spec")
    for name in (*CATALOGS, "overrides.json", "prose.json"):
        if _newer(_mtime(dest, name), spec_t):
            lines.append(f"the spec predates {name}: re-run render.py spec")
    if _newer(ledger_t, spec_t) and _coverage_differs(dest, spec_name):
        lines.append("the spec predates ledger.json: re-run render.py spec")
    if _newer(spec_t, _mtime(dest, "grade.json")):
        lines.append("the grade predates the spec: run grade.py")
    if _newer(spec_t, _mtime(dest, "review.json")):
        lines.append("the review predates the spec: run review")
    return lines


def _gates(dest, blocking):
    """The gates that fail, each named with what fails: the ledger's classes, the grader's checks, the findings."""
    failing = []
    led = out.load(dest, "ledger.json", None)
    if isinstance(led, dict) and led.get("pass") is False:
        classes = led.get("classes") if isinstance(led.get("classes"), dict) else {}
        names = [k for k, v in classes.items() if isinstance(v, dict) and v.get("pass") is False]
        failing.append(f"the ledger fails ({', '.join(names) or 'see LEDGER.md'})")
    grade = out.load(dest, "grade.json", None)
    if isinstance(grade, dict) and grade.get("pass") is False:
        checks = grade.get("checks") if isinstance(grade.get("checks"), list) else []
        names = [str(c.get("name")) for c in checks if isinstance(c, dict) and c.get("pass") is False]
        failing.append(f"the grade fails ({', '.join(names) or 'see grade.json'})")
    if blocking:
        failing.append(f"{blocking} Blocker/High finding(s) remain")
    return failing


def _review(dest):
    """(passes, remaining Blocker and High findings of the last pass)."""
    doc = out.load(dest, "review.json", {})
    passes = [p for p in ((doc.get("passes") if isinstance(doc, dict) else None) or []) if isinstance(p, dict)]
    if not passes:
        return 0, 0
    critic = [c for c in (passes[-1].get("critic") or []) if isinstance(c, dict)]
    return len(passes), sum(1 for c in critic if c.get("severity") in ("Blocker", "High"))


def _coverage(dest):
    doc = out.load(dest, "ledger.json", None)
    classes = doc.get("classes") if isinstance(doc, dict) else None
    if not isinstance(classes, dict):
        return None
    return {k: v.get("percent") for k, v in classes.items() if isinstance(v, dict)}


def _next(dest, cfg, stages, stale, spec_name, blocking=0):
    q = shlex.quote(dest)
    skill = f"/app-spec:spec {q}"
    name_arg = "" if spec_name == DEFAULT_SPEC else f" --name {shlex.quote(spec_name)}"  # else render and grade use SPEC.md
    if not stages["module"]["status"] == "done":
        app_cfg, module_cfg = cfg.get("app"), cfg.get("module")
        app = (app_cfg.get("path") if isinstance(app_cfg, dict) else None) or "<app>"
        query = module_cfg.get("query") if isinstance(module_cfg, dict) else None
        if not isinstance(app, str):
            app = "<app>"
        modules = " ".join(f"--module {shlex.quote(str(m))}" for m in query) if isinstance(query, list) and query \
            else "--module <name>"
        return f"{script('module.py')} {shlex.quote(app) if app != '<app>' else app} {modules} --out {q}", \
            "no module is set up yet"
    if stages["inventory"]["status"] != "done":
        return f"{script('inventory.py')} {q}", "count what the module holds"
    if stages["understand"]["status"] != "done":
        return f"{skill}  (run the understand workflow from /app-spec:spec)", "the understand workflow has no result yet"
    if stages["rules"]["status"] != "done":
        return f"{skill}  (run the rules workflow from /app-spec:spec)", "the rules workflow has no result yet"
    if stages["catalogs"]["status"] != "done":
        return f"{script('render.py')} catalogs {q}", "the workflow results are not rendered into catalogs yet"
    if stages["contracts"]["status"] != "done":
        return f"{script('contracts.py')} {q}", "contract repositories are configured and not read yet"
    if stages["spec"]["status"] != "done":
        return f"{script('render.py')} spec {q}{name_arg}", f"{spec_name} is not written yet"
    if stages["review"]["status"] != "done":
        return f"/app-spec:review {q}", "the spec has no review yet"
    # Everything exists: the first stale step in pipeline order. A pass runs ledger, spec, grade; the review runs the
    # ledger and the grader itself, so a stale review comes before a stale grade.
    for prefix, command in (("the inventory", f"{script('inventory.py')} {q}"),
                            ("the catalogs", f"{script('render.py')} catalogs {q}"),
                            ("the ledger", f"{script('ledger.py')} {q}"),
                            ("the spec predates", f"{script('render.py')} spec {q}{name_arg}"),
                            ("the review", f"/app-spec:review {q}"),
                            ("the grade", f"{script('grade.py')} {q}{name_arg}")):
        for line in stale:
            if line.startswith(prefix):
                return command, line
    failing = _gates(dest, blocking)
    if failing:
        return f"/app-spec:review {q}", "; ".join(failing) + ": fix the spec or regenerate it, then review it again"
    return f"(a person) read {spec_name}", "the spec is ready for a person"


def report(dest):
    """The state of the output folder `dest` as a dict: stages, stale, coverage, passes, blocking and next."""
    _check_folder(dest)
    cfg = _config(dest)
    spec_name = _spec_name(cfg)
    stages = _stages(dest, cfg, spec_name)
    stale = _stale(dest, spec_name)
    passes, blocking = _review(dest)
    command, reason = _next(dest, cfg, stages, stale, spec_name, blocking)
    result = {"out": dest, "spec": spec_name, "stages": stages, "stale": stale, "coverage": _coverage(dest),
              "passes": passes, "blocking": blocking, "next": {"command": command, "reason": reason}}
    options = cfg.get("options")
    if isinstance(options, dict) and options.get("independence") == "single-agent":
        result["independence"] = "single-agent"
    return result


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: status.py <out> [--json]", file=sys.stderr)
        return 2
    r = report(args[0])
    if as_json:
        print(json.dumps(r, indent=2, default=str))
        return 0
    print(f"Output {r['out']}")
    if r.get("independence") == "single-agent":
        print("  independence: single-agent")
    for name, s in r["stages"].items():
        when = datetime.fromtimestamp(s["mtime"]).strftime("%Y-%m-%d %H:%M") if s["mtime"] else "-"
        print(f"  {name:<11} {s['status']:<5} {when}")
    if r["coverage"]:
        print("  coverage: " + ", ".join(f"{k} {v}%" for k, v in r["coverage"].items()))
    if r["passes"]:
        print(f"  review: {r['passes']} pass(es), {r['blocking']} Blocker/High finding(s) left")
    for line in r["stale"]:
        print(f"  stale: {line}")
    print(f"Next: {r['next']['command']}")
    print(f"      ({r['next']['reason']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
