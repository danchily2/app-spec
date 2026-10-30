"""The fixed shape of the spec: headings, appendices, the acceptance-criterion line, and the header lines."""

HEADINGS = [
    "## Summary",
    "## Capabilities",
    "## Screens",
    "## Endpoints",
    "## Business rules and permissions",
    "## Acceptance criteria",
    "## Dependencies and decisions",
    "## Open questions",
]

APPENDICES = [
    "## Appendix A. Fields and ids",
    "## Appendix B. Data",
    "## Appendix C. Behaviour to keep, implementation to drop",
    "## Appendix D. Strings, analytics and platform",
    "## Appendix E. Flows",
    "## Appendix F. Coverage",
]

AC_RE = r"^- \*\*AC(\d+) \(((?:UC|CAP)-\d{3,})(?:, (?:UC|CAP)-\d{3,})*\):\*\* .+"

SOURCE_EXT = ("swift", "kt", "java", "ts", "tsx", "js", "jsx", "m", "h", "cs", "py", "xml", "json", "plist", "strings",
              "xcstrings", "gradle", "kts", "yml", "yaml", "md")

# a citation: a path with a `/` or a source-file extension, a colon, a line or a line range. A host with a port is not one.
CITE_RE = (r"(?:[\w@+.\-]+/)*[\w@+.\-]*(?:\.(?:" + "|".join(SOURCE_EXT) + r")(?![\w])|/[\w@+.\-]+)"
           r":\d+(?:-\d+)?")

EVIDENCE_LABELS = ("VERIFIED", "INFERRED", "UNKNOWN", "PROPOSED")


def module_name(cfg):
    """The module as the header names it: the query the person gave, else the app name."""
    query = [str(q) for q in (cfg.get("module") or {}).get("query") or []]
    return ", ".join(query) or cfg["app"]["name"]


def header(cfg):
    """The title and the `Source:` and `Reference HEADs:` lines, as text with a trailing newline.

    The app comes first on the `Reference HEADs:` line, then one entry per contract repository."""
    app = cfg["app"]
    entries = [f"{app['name']} `{app.get('commit') or 'UNKNOWN'}`"]
    entries += [f"{c.get('name') or 'contract'} `{c.get('commit') or 'UNKNOWN'}`" for c in cfg.get("contracts") or []]
    module = module_name(cfg)
    return "\n".join([f"# {module} spec", "",
                      f"Source: module {module} of {app['name']} (no source issue)",
                      f"Reference HEADs: {', '.join(entries)}"]) + "\n"
