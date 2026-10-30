"""Field inventory: the UI elements of each screen, with the string key, text and accessibility id they already have.

`extract(stack, app_root, files)` returns `[{"screen", "file": "rel:line", "elements": [...]}]` in the shape of
`fields.json`. Every stack has one function that finds the screens of a file and one that finds the elements of a
screen. The scan is textual, like the extractors: it reads what the code states and leaves a field `null` when neither
a key nor a literal is visible.
"""

import os
import re

from .common import line_of, match_brace, read_text, strip_comments

SWIFTUI_KINDS = {"Text": "text", "TextField": "input", "SecureField": "input", "Button": "button", "Toggle": "toggle",
                 "Picker": "picker", "DatePicker": "picker", "List": "list", "ForEach": "list", "Image": "image",
                 "AsyncImage": "image", "QuickLookPreview": "document", "PDFKitView": "document"}
UIKIT_KINDS = {"UILabel": "text", "UITextField": "input", "UITextView": "input", "UIButton": "button",
               "UISwitch": "toggle", "UIPickerView": "picker", "UIDatePicker": "picker", "UITableView": "list",
               "UICollectionView": "list", "UIImageView": "image"}
COMPOSE_KINDS = {"Text": "text", "TextField": "input", "OutlinedTextField": "input", "Button": "button",
                 "IconButton": "button", "TextButton": "button", "Switch": "toggle", "Checkbox": "toggle",
                 "DropdownMenu": "picker", "LazyColumn": "list", "LazyRow": "list", "Image": "image", "Icon": "image"}
RN_KINDS = {"Text": "text", "TextInput": "input", "Button": "button", "Pressable": "button",
            "TouchableOpacity": "button", "Switch": "toggle", "Picker": "picker", "FlatList": "list",
            "SectionList": "list", "Image": "image"}

SOURCE_EXTS = {"ios-native": (".swift",), "android-native": (".kt",), "react-native": (".tsx", ".jsx", ".ts", ".js")}

_IDENTIFIER = [re.compile(p) for p in (
    r"\.accessibilityIdentifier\(\s*\"([^\"]*)\"\s*\)",
    r"accessibilityIdentifier\s*=\s*\"([^\"]*)\"",
    r"testTag\(\s*\"([^\"]*)\"",
    r"testID\s*=\s*(?:\{\s*)?[\"']([^\"']*)[\"']",
)]
_TEXT_KEY = [re.compile(p) for p in (
    r"\bL10n\.([A-Za-z_][\w.]*)",
    r"String\(\s*localized:\s*\"([^\"]+)\"",
    r"NSLocalizedString\(\s*\"([^\"]+)\"",
    r"\bStrings\.([A-Za-z_][\w.]*)",
    r"stringResource\(\s*(?:id\s*=\s*)?R\.string\.(\w+)",
    r"\bt\(\s*'([^']+)'",
    r"\bt\(\s*\"([^\"]+)\"",
)]
_NAMED_ATTR = re.compile(r"\b(?:title|placeholder)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_POSITIONAL_LITERAL = re.compile(r"\s*\"((?:[^\"\\]|\\.)*)\"")
_NAMED_LITERAL = re.compile(r"\b(?:text|title|label|placeholder|verbatim)\s*[:=]\s*\"((?:[^\"\\]|\\.)*)\"")
_SWIFT_DECL = re.compile(r"^(?:@\w+(?:\([^)]*\))?\s+)*(?:(?:public|internal|private|fileprivate|open|final)\s+)*"
                         r"(?:struct|class)\s+(\w+)\s*(?:<[^>]*>)?\s*:\s*([^{\n]+)\{", re.M)
_COMPOSABLE = re.compile(r"^@Composable\b[^\n]*\n(?:@\w+[^\n]*\n)*(?:(?:private|internal|public)\s+)?fun\s+(\w+)\s*\(", re.M)
_RN_DECL = re.compile(r"^(export\s+default\s+|export\s+)?(?:async\s+)?(?:const|function|class)\s+([A-Z]\w*)", re.M)
_RN_DEFAULT_NAME = re.compile(r"^export\s+default\s+(?:React\.)?(?:memo\(|observer\()?\s*([A-Z]\w*)", re.M)


def _unquote(value):
    return value.replace('\\"', '"')


def _first(patterns, text):
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def _literal(args):
    """The literal text a call passes: its first argument when that is a string, else a named text argument."""
    m = _POSITIONAL_LITERAL.match(args) or _NAMED_LITERAL.search(args)
    return _unquote(m.group(1)) if m else None


def _element(kind, args, region, rel, text, index):
    """One element. `args` holds the text and key, `region` also the modifiers that carry the identifier."""
    return {"kind": kind, "textKey": _first(_TEXT_KEY, args), "text": _literal(args),
            "identifier": _first(_IDENTIFIER, region), "file": rel, "line": line_of(text, index)}


def _screen(name, rel, text, index, elements):
    return {"screen": name, "file": f"{rel}:{line_of(text, index)}", "elements": elements}


# ---------------------------------------------------------------- calls: SwiftUI and Compose

def _call(text, name_end, limit):
    """Arguments and modifier chain of the call whose name ends at `name_end`.

    Returns (args, region, end). `region` is the arguments plus the `.modifier(...)` lines that follow, so an
    identifier set on the next element is never read as this element's. Trailing closures are skipped: what they
    hold belongs to the elements inside them. Returns None for a name that is not followed by `(` or `{`.
    """
    i = name_end
    while i < limit and text[i] in " \t":
        i += 1
    args = ""
    if i < limit and text[i] == "(":
        close = match_brace(text, i, "(", ")")
        if close < 0 or close >= limit:
            return None
        args = text[i + 1:close]
        i = close + 1
    elif not (i < limit and text[i] == "{"):
        return None
    chain = ""
    while True:
        j = i
        while j < limit and text[j] in " \t":
            j += 1
        if j < limit and text[j] == "{":  # a trailing closure on the same line
            close = match_brace(text, j)
            if close < 0 or close >= limit:
                break
            i = close + 1
            continue
        k = j
        while k < limit and text[k] in " \t\r\n":
            k += 1
        step = re.match(r"\.[A-Za-z_]\w*|\w+\s*:(?=\s*\{)", text[k:limit])
        if text.count("\n", j, k) >= 2 or not step:  # a blank line, or no modifier or labelled closure next
            break
        name_start = k
        k += step.end()
        while k < limit and text[k] in " \t":
            k += 1
        if k < limit and text[k] in "({":
            opener = text[k]
            close = match_brace(text, k, opener, ")" if opener == "(" else "}")
            if close < 0 or close >= limit:
                break
            if opener == "(":
                chain += text[name_start:close + 1]
            k = close + 1
        i = k
    return args, args + chain, i


def _scan_calls(text, start, end, kinds, rel):
    elements = []
    pattern = re.compile(r"(?<![\w.])(" + "|".join(sorted(kinds, key=len, reverse=True)) + r")\b")
    for m in pattern.finditer(text, start, end):
        call = _call(text, m.end(), end)
        if call is None:
            continue
        args, region, _ = call
        elements.append(_element(kinds[m.group(1)], args, region, rel, text, m.start()))
    return elements


# ---------------------------------------------------------------- iOS

def _uikit_elements(text, start, end, rel):
    """UILabel() style elements. The statements `name.text = ...` that follow carry the key, text and identifier."""
    pattern = re.compile(r"(?<![\w.])(" + "|".join(sorted(UIKIT_KINDS, key=len, reverse=True)) + r")\s*\(")
    elements = []
    for m in pattern.finditer(text, start, end):
        close = match_brace(text, m.end() - 1, "(", ")")
        line_start = text.rfind("\n", 0, m.start()) + 1
        decl = re.search(r"(?:let|var)\s+(\w+)\b", text[line_start:m.start()])
        name = decl.group(1) if decl else None
        statements = ""
        if name:
            statements = "\n".join(s.group(0) for s in re.finditer(
                r"(?:self\.)?\b" + re.escape(name) + r"\.(?:\w+\s*=[^\n;]*|setTitle\([^\n]*)", text[start:end]))
        args = (text[m.end():close] if close > 0 else "") + "\n" + statements
        literal = re.search(r"\.setTitle\(\s*\"((?:[^\"\\]|\\.)*)\"|\.(?:text|placeholder)\s*=\s*\"((?:[^\"\\]|\\.)*)\"", statements)
        elements.append({"kind": UIKIT_KINDS[m.group(1)], "textKey": _first(_TEXT_KEY, args),
                         "text": _unquote(literal.group(1) or literal.group(2)) if literal else None,
                         "identifier": _first(_IDENTIFIER, args), "file": rel, "line": line_of(text, m.start())})
    return elements


def _ios(rel, text):
    screens = []
    for m in _SWIFT_DECL.finditer(text):
        conforms = [c.strip().split(".")[-1] for c in m.group(2).split(",")]
        is_view = "View" in conforms
        is_controller = bool(conforms) and conforms[0].endswith("ViewController")
        if not (is_view or is_controller):
            continue
        open_index = m.end() - 1
        close = match_brace(text, open_index)
        end = close if close > 0 else len(text)
        elements = (_scan_calls(text, open_index, end, SWIFTUI_KINDS, rel) if is_view
                    else _uikit_elements(text, open_index, end, rel))
        screens.append(_screen(m.group(1), rel, text, m.start(), elements))
    return screens


# ---------------------------------------------------------------- Android

def _android(rel, text):
    screens = []
    for m in _COMPOSABLE.finditer(text):
        name = m.group(1)
        if not name.endswith(("Screen", "View")):
            continue
        paren = m.end() - 1
        params_end = match_brace(text, paren, "(", ")")
        brace = text.find("{", params_end if params_end > 0 else paren)
        if brace < 0:
            continue
        close = match_brace(text, brace)
        end = close if close > 0 else len(text)
        screens.append(_screen(name, rel, text, m.start(), _scan_calls(text, brace, end, COMPOSE_KINDS, rel)))
    return screens


# ---------------------------------------------------------------- React Native

def _tag_end(text, i):
    """Index of the `>` that closes the opening tag whose attributes start at `i`, or -1."""
    depth, quote = 0, None
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                quote = None
        elif depth == 0 and c in "\"'":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return i
        i += 1
    return -1


def _rn_elements(text, start, end, rel):
    elements = []
    pattern = re.compile(r"<(" + "|".join(sorted(RN_KINDS, key=len, reverse=True)) + r")(?=[\s/>])")
    for m in pattern.finditer(text, start, end):
        close = _tag_end(text, m.end())
        if close < 0:
            continue
        tag = text[m.end():close]
        children = ""
        if not tag.rstrip().endswith("/") and m.group(1) == "Text":
            stop = text.find("</Text>", close)
            children = text[close + 1:stop] if stop > 0 else ""
        literal = _NAMED_ATTR.search(tag)
        plain = children.strip() if children and not re.search(r"[{<]", children) else ""
        elements.append({"kind": RN_KINDS[m.group(1)], "textKey": _first(_TEXT_KEY, tag + " " + children),
                         "text": _unquote(literal.group(1) or literal.group(2)) if literal else (plain or None),
                         "identifier": _first(_IDENTIFIER, tag), "file": rel, "line": line_of(text, m.start())})
    return elements



def _rn(rel, text):
    declared = [(m, m.group(2)) for m in _RN_DECL.finditer(text)]
    default = _RN_DEFAULT_NAME.search(text)
    default_name = default.group(1) if default else None
    screens = []
    for m, name in declared:
        is_default = bool(m.group(1) and "default" in m.group(1)) or name == default_name
        if not (is_default or name.endswith(("Screen", "View"))):
            continue
        following = [n.start() for n, _ in declared if n.start() > m.start()]
        end = following[0] if following else len(text)
        screens.append(_screen(name, rel, text, m.start(), _rn_elements(text, m.end(), end, rel)))
    if default is None and not screens:
        anon = re.search(r"^export\s+default\s+(?:function|class|\()", text, re.M)
        if anon:
            screens.append(_screen(os.path.splitext(os.path.basename(rel))[0], rel, text, anon.start(),
                                   _rn_elements(text, anon.end(), len(text), rel)))
    return screens


# ---------------------------------------------------------------- entry point

_STACKS = {"ios-native": _ios, "android-native": _android, "react-native": _rn}


def extract(stack, app_root, files):
    """The screens of `files` (absolute, or relative to `app_root`) with their elements.

    Raises ValueError for a stack with no field scan. Files that are not source of the stack are skipped.
    """
    if stack not in _STACKS:
        raise ValueError(f"no field inventory for stack {stack!r}")
    scan = _STACKS[stack]
    root = os.path.realpath(app_root)
    found = []
    for path in files:
        full = os.path.realpath(os.path.join(root, path))
        if not full.endswith(SOURCE_EXTS[stack]):
            continue
        text = read_text(full)
        if text is None:
            continue
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        found.append((rel, scan(rel, strip_comments(text))))
    return [s for _, screens in sorted(found, key=lambda x: x[0]) for s in screens]
