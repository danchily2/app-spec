"""Derive the builder spec from the evidence spec: the same text with every `path:line` citation taken out.

A pure function of the evidence text. Fenced code is never touched. Citations are removed from prose, from the cells of
tables and from labelled bullets, and the words around them are tidied so no empty parentheses, stray commas or double
spaces are left behind. Appendix F is replaced by a pointer to the evidence file, which keeps every citation."""

import re

from .template import APPENDICES, CITE_RE

# CITE_RE already ends in the line or line range, so it is the whole citation pattern
CITATION = re.compile(CITE_RE)
# a citation may list more lines of the same file: A.swift:20,40-44,90
_MORE_LINES = r"(?:,\d+(?:-\d+)?)*"
_BARE = re.compile(CITE_RE + _MORE_LINES)

_SEPARATOR = re.compile(r"^\s*\|[\s:|\-]+\|\s*$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_LABELLED_BULLET = re.compile(r"^\s*- \*\*(?:Source|Evidence|Citations?):\*\*")
_ONLY_CONNECTORS = re.compile(r"[\s,;.]*(?:and[\s,;.]*)*")
_EMPTY_PAREN = re.compile(r" ?\((?:[\s,;]|\band\b|\bcites\b|\bsee\b|\bin\b)*\)")
# a label with nothing after it but punctuation: the end of the line, a full stop, or a closing parenthesis
_EMPTY_LABEL = re.compile(r"\s*\b(?:Source|Evidence|Searched|Cited in):[\s,;]*(?:\.(?=\s|$)|$|(?=\)))")
_CODE_SPAN = re.compile(r"`([^`\n]*)`")
_HANGING_SEE = re.compile(r"[,;]?\s+see(?=\s*(?:[.,;)]|$))")
_CARRY_AS_IS = re.compile(r"carry-as-is \([^)]*\)")
_SEARCHED = re.compile(r"(UNKNOWN; )searched: .*?; (?=owner:)")
_DROPPED_COLUMNS = ("Source", "Evidence")


def evidence_name(name):
    """`payslips.md` -> `payslips.evidence.md`; a name without `.md` gets `.evidence.md` appended."""
    return (name[:-3] if name.endswith(".md") else name) + ".evidence.md"


def outside_code(text):
    """Yield (1-based line number, line) for every line that is not a fence line or inside a fenced block."""
    fenced = False
    for number, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            yield number, line


def _span_without_citation(match):
    """A code span that holds a citation loses it; a span left empty or with one plain word is dropped whole."""
    inner = match.group(1)
    if not _BARE.search(inner):
        return match.group(0)
    rest = re.sub(r"\s+", " ", _BARE.sub("", inner)).strip()
    return "" if re.fullmatch(r"[A-Za-z][\w-]*|", rest) else f"`{rest}`"


def _remove_citations(line):
    return _BARE.sub("", _CODE_SPAN.sub(_span_without_citation, line))


def _tidy(line):
    """Remove what a taken-out citation leaves behind, until the line stops changing."""
    previous = None
    while previous != line:
        previous = line
        line = _EMPTY_PAREN.sub("", line)
        line = _EMPTY_LABEL.sub("", line)
        line = line.replace(", ,", ",").replace(" ,", ",").replace(" .", ".").replace(" ;", ";")
        line = re.sub(r"[,;]\s*\)", ")", line)
        line = _HANGING_SEE.sub("", line)
        line = re.sub(r"[,;]\.", ".", line)
        line = re.sub(r"\(\s*[,;]\s*", "(", line)
        line = re.sub(r"(?<=\S)  +", " ", line)
    return line.rstrip()


def _strip_line(line):
    """Rules 4 and 5 for one line. A line that held nothing but citations comes back as None."""
    line = _SEARCHED.sub(r"\1", line)
    stripped = _remove_citations(line)
    if stripped == line:
        return line
    stripped = _tidy(stripped)
    return stripped if stripped.strip() else None


def _cells(line):
    return _CELL_SPLIT.split(line)


def _dropped_columns(header):
    return {i for i, cell in enumerate(_cells(header)) if cell.strip() in _DROPPED_COLUMNS}


def _table_row(line, dropped, design):
    cells = _cells(line)
    if design is not None and design < len(cells):
        cells[design] = _CARRY_AS_IS.sub("carry-as-is", cells[design])
    return "|".join(c for i, c in enumerate(cells) if i not in dropped)


def builder_text(evidence, evidence_name):
    """The evidence spec without citations. `evidence_name` is the file the Appendix F pointer names."""
    lines = evidence.split("\n")
    trailing_newline = evidence.endswith("\n")
    if trailing_newline:
        lines.pop()
    outside = dict(outside_code(evidence))
    out = []
    dropped, design = None, None  # the table being copied: its dropped column indexes and its Design column
    in_scope = in_appendix_f = False
    for number, line in enumerate(lines, 1):
        is_outside = number in outside
        if in_appendix_f:
            if not (is_outside and line.startswith("## ")):
                continue
            in_appendix_f = False
            out.append("")
        if not is_outside:
            out.append(line)
            continue
        if in_scope:
            if line.strip():
                continue
            in_scope = False
            continue
        if line.strip() == "Module scope:":
            in_scope = True
            continue
        if line.strip() == APPENDICES[5]:
            out += [line, "", f"Coverage evidence and every citation: `{evidence_name}`."]
            in_appendix_f = True
            continue
        if dropped is not None and not line.lstrip().startswith("|"):
            dropped, design = None, None
        if dropped is None and line.lstrip().startswith("|") and number < len(lines) \
                and _SEPARATOR.match(lines[number]):
            dropped = _dropped_columns(line)
            header = [c.strip() for c in _cells(line)]
            design = header.index("Design") if "Design" in header else None
        if dropped is not None:
            line = _table_row(line, dropped, design)
        elif _LABELLED_BULLET.match(line):
            rest = _remove_citations(line[_LABELLED_BULLET.match(line).end():])
            if _ONLY_CONNECTORS.fullmatch(rest):
                continue
        stripped = _strip_line(line)
        if stripped is not None:
            out.append(stripped)
    return "\n".join(out) + ("\n" if trailing_newline else "")
