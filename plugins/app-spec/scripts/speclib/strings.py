"""Parse app string catalogs into one shape: {format, files, locales, source, keys: {key: [locales]}, values: {key: text}}.

Formats: i18next-style JSON (flat or nested, one file per locale or one folder per locale), Apple String Catalogs
(.xcstrings), legacy Apple .strings in *.lproj folders, Android res/values*/strings.xml, and Flutter .arb files.
`values` holds the source locale's text only: it is what a Figma text is matched against.
"""

import json
import os
import re
import xml.etree.ElementTree as ET

from .common import EXCLUDE_DIRS, read_text

LOCALE = re.compile(r"^(?:[a-z]{2,3})(?:[-_](?:[A-Z]{2}|[a-z]{2}|[A-Z][a-z]{3}|[0-9]{3}))?$")
_STRINGS_LINE = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*=\s*"((?:[^"\\]|\\.)*)"\s*;', re.M)


def _flatten_strings(obj):
    flat = {}

    def rec(value, prefix):
        if isinstance(value, dict):
            for k, v in value.items():
                rec(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(value, (str, int, float)):
            flat[prefix] = str(value)
        elif isinstance(value, list):
            flat[prefix] = " / ".join(str(v) for v in value if isinstance(v, (str, int, float)))

    rec(obj, "")
    return flat


def _new_catalog(fmt):
    return {"format": fmt, "files": [], "locales": [], "source": None, "keys": {}, "values": {}}


def _merge(catalog, locale, flat, rel):
    if rel not in catalog["files"]:
        catalog["files"].append(rel)
    if locale not in catalog["locales"]:
        catalog["locales"].append(locale)
    for key in flat:
        locs = catalog["keys"].setdefault(key, [])
        if locale not in locs:
            locs.append(locale)


def _choose_source(catalog, flats):
    catalog["allValues"] = {loc: {k: v for k, v in flat.items() if isinstance(v, str)} for loc, flat in flats.items()}
    if not catalog["locales"]:
        return
    preferred = next((l for l in catalog["locales"] if l.split("-")[0].split("_")[0] == "en"), None)
    source = preferred or max(catalog["locales"], key=lambda l: len(flats.get(l, {})))
    catalog["source"] = source
    catalog["values"] = {k: v for k, v in flats.get(source, {}).items() if isinstance(v, str)}


def _walk_dirs(root):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)
        yield dirpath, dirnames, sorted(filenames)


def find_i18n_json(root, include=None):
    """i18next-style catalogs: a folder with >= 2 '<locale>.json' files, or a folder of '<locale>/' folders of JSON.

    `include` limits the search to top-level folders (for React Native: src, app, assets, locales, translations)."""
    catalog = _new_catalog("i18n-json")
    flats = {}
    tops = include or ["."]
    for top in tops:
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in _walk_dirs(base):
            locale_files = [f for f in filenames if f.endswith(".json") and LOCALE.match(f[:-5])]
            if len(locale_files) >= 2:
                for fname in locale_files:
                    full = os.path.join(dirpath, fname)
                    text = read_text(full)
                    try:
                        data = json.loads(text) if text else None
                    except ValueError:
                        data = None
                    if not isinstance(data, dict):
                        continue
                    flat = _flatten_strings(data)
                    loc = fname[:-5]
                    flats.setdefault(loc, {}).update(flat)
                    _merge(catalog, loc, flat, os.path.relpath(full, root).replace(os.sep, "/"))
            locale_dirs = [d for d in dirnames if LOCALE.match(d)]
            if len(locale_dirs) >= 2:
                for loc in locale_dirs:
                    for fname in sorted(os.listdir(os.path.join(dirpath, loc))):
                        if not fname.endswith(".json"):
                            continue
                        full = os.path.join(dirpath, loc, fname)
                        text = read_text(full)
                        try:
                            data = json.loads(text) if text else None
                        except ValueError:
                            data = None
                        if not isinstance(data, dict):
                            continue
                        ns = fname[:-5]
                        flat = {f"{ns}:{k}": v for k, v in _flatten_strings(data).items()}
                        flats.setdefault(loc, {}).update(flat)
                        _merge(catalog, loc, flat, os.path.relpath(full, root).replace(os.sep, "/"))
    _choose_source(catalog, flats)
    return catalog if catalog["files"] else None


def parse_xcstrings(root, files):
    """Apple String Catalogs. A key with no localization of the source language uses the key itself as its text."""
    catalog = _new_catalog("xcstrings")
    flats = {}
    for rel in files:
        text = read_text(os.path.join(root, rel))
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            continue
        source = data.get("sourceLanguage") or "en"
        catalog["files"].append(rel)
        if source not in catalog["locales"]:
            catalog["locales"].append(source)
        for key, entry in (data.get("strings") or {}).items():
            locs = catalog["keys"].setdefault(key, [])
            locals_ = (entry or {}).get("localizations") or {}
            if source not in locs:
                locs.append(source)
            for loc, body in locals_.items():
                if loc not in catalog["locales"]:
                    catalog["locales"].append(loc)
                if loc not in locs:
                    locs.append(loc)
                unit = (body or {}).get("stringUnit") or {}
                value = unit.get("value")
                if value is None and "variations" in (body or {}):
                    plural = ((body.get("variations") or {}).get("plural") or {})
                    value = ((plural.get("other") or {}).get("stringUnit") or {}).get("value")
                if value is not None:
                    flats.setdefault(loc, {})[key] = value
            flats.setdefault(source, {}).setdefault(key, key)
    catalog["source"] = next(iter(catalog["locales"]), None)
    catalog["allValues"] = {loc: {k: v for k, v in flat.items() if isinstance(v, str)} for loc, flat in flats.items()}
    if catalog["source"]:
        catalog["values"] = {k: v for k, v in flats.get(catalog["source"], {}).items() if isinstance(v, str)}
    return catalog if catalog["files"] else None


def parse_lproj_strings(root, files):
    """Legacy Apple Localizable.strings files in <locale>.lproj folders."""
    catalog = _new_catalog("apple-strings")
    flats = {}
    for rel in files:
        parts = rel.split("/")
        lproj = next((p for p in reversed(parts[:-1]) if p.endswith(".lproj")), None)
        if not lproj:
            continue
        loc = lproj[:-6]
        if loc == "Base":
            loc = "base"
        text = read_text(os.path.join(root, rel)) or ""
        flat = {m.group(1): m.group(2) for m in _STRINGS_LINE.finditer(text)}
        if not flat:
            continue
        ns = parts[-1][:-8] if parts[-1].endswith(".strings") else parts[-1]
        flat = {(k if ns == "Localizable" else f"{ns}:{k}"): v for k, v in flat.items()}
        flats.setdefault(loc, {}).update(flat)
        _merge(catalog, loc, flat, rel)
    _choose_source(catalog, flats)
    return catalog if catalog["files"] else None


def parse_android_strings(root, files):
    """res/values[-xx]/strings.xml (and other values XML with <string> or <plurals>)."""
    catalog = _new_catalog("android-xml")
    flats = {}
    for rel in files:
        folder = rel.split("/")[-2] if "/" in rel else ""
        if not folder.startswith("values"):
            continue
        qual = folder[len("values"):].lstrip("-")
        loc = "default"
        if qual:
            first = qual.split("-")[0]
            if re.match(r"^[a-z]{2,3}$", first):
                region = next((q[1:] for q in qual.split("-")[1:] if re.match(r"^r[A-Z]{2}$", q)), None)
                loc = f"{first}-{region}" if region else first
            elif qual.startswith("b+"):
                loc = qual[2:].replace("+", "-")
            else:
                continue  # values-night, values-v21, values-sw600dp ... are not locales
        text = read_text(os.path.join(root, rel))
        if not text or "<string" not in text and "<plurals" not in text:
            continue
        try:
            tree = ET.fromstring(text)
        except ET.ParseError:
            continue
        flat = {}
        for el in tree:
            if el.tag == "string" and el.get("name") and el.get("translatable") != "false":
                flat[el.get("name")] = "".join(el.itertext()).strip()
            elif el.tag == "plurals" and el.get("name"):
                other = next((i for i in el if i.get("quantity") == "other"), None)
                flat[el.get("name")] = "".join(other.itertext()).strip() if other is not None else ""
        if not flat:
            continue
        flats.setdefault(loc, {}).update(flat)
        _merge(catalog, loc, flat, rel)
    if catalog["files"]:
        catalog["source"] = "default" if "default" in catalog["locales"] else catalog["locales"][0]
        catalog["values"] = {k: v for k, v in flats.get(catalog["source"], {}).items() if isinstance(v, str)}
        catalog["allValues"] = {loc: {k: v for k, v in flat.items() if isinstance(v, str)} for loc, flat in flats.items()}
    return catalog if catalog["files"] else None


def parse_arb(root, files):
    catalog = _new_catalog("arb")
    flats = {}
    for rel in files:
        m = re.search(r"_([a-z]{2,3}(?:_[A-Z]{2})?)\.arb$", rel)
        if not m:
            continue
        text = read_text(os.path.join(root, rel))
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        if not isinstance(data, dict):
            continue
        flat = {k: v for k, v in data.items() if not k.startswith("@") and isinstance(v, str)}
        flats.setdefault(m.group(1), {}).update(flat)
        _merge(catalog, m.group(1), flat, rel)
    _choose_source(catalog, flats)
    return catalog if catalog["files"] else None


def combine(*catalogs):
    """Merge several catalogs of one app (for example xcstrings plus a legacy .strings file)."""
    parts = [c for c in catalogs if c]
    if not parts:
        return {"format": "none", "files": [], "locales": [], "source": None, "keys": {}, "values": {}, "allValues": {}}
    if len(parts) == 1:
        return parts[0]
    out = {"format": "+".join(p["format"] for p in parts), "files": [], "locales": [], "source": parts[0]["source"],
           "keys": {}, "values": {}, "allValues": {}}
    for p in parts:
        out["files"] += p["files"]
        for loc in p["locales"]:
            if loc not in out["locales"]:
                out["locales"].append(loc)
        for key, locs in p["keys"].items():
            merged = out["keys"].setdefault(key, [])
            merged.extend(l for l in locs if l not in merged)
        for key, value in p["values"].items():
            out["values"].setdefault(key, value)
        for loc, vals in (p.get("allValues") or {}).items():
            merged_vals = out["allValues"].setdefault(loc, {})
            for key, value in vals.items():
                merged_vals.setdefault(key, value)
    return out


def summary(catalog):
    """Counts for an inventory: keys (union of locales), per-locale key counts, missing per locale."""
    keys = catalog.get("keys") or {}
    per_locale = {loc: 0 for loc in catalog.get("locales", [])}
    for locs in keys.values():
        for loc in locs:
            per_locale[loc] = per_locale.get(loc, 0) + 1
    return {
        "format": catalog.get("format"),
        "files": catalog.get("files", []),
        "locales": catalog.get("locales", []),
        "source": catalog.get("source"),
        "keys": len(keys),
        "perLocale": per_locale,
        "missingPerLocale": {loc: len(keys) - n for loc, n in per_locale.items()},
    }


NORWEGIAN = {"no", "nb", "nn"}


def base_locale(code):
    """Compare locales by what users read. 'nb-NO', 'no' and 'nb' are Norwegian Bokmål ('nb'); 'da-DK' is 'da'. Chinese
    keeps its script (zh-hans, zh-hant) and Portuguese its region (pt-br, pt), because those differ for their users.
    Apple's Base and Android's default folder hold the development language: 'base' and 'default' stay as they are,
    and the parity checks read them as English unless the catalog says otherwise."""
    if not code:
        return ""
    parts = [p for p in str(code).replace("_", "-").replace("+", "-").lower().split("-") if p]
    if parts and parts[0] == "b" and len(parts) > 1:  # Android BCP 47 folders: values-b+zh+Hant+TW
        parts = parts[1:]
    if not parts:
        return ""
    lang, rest = parts[0], [p[1:] if len(p) == 3 and p.startswith("r") else p for p in parts[1:]]
    if lang in ("no", "nb"):
        return "nb"
    if lang == "zh":
        return "zh-hant" if "hant" in rest or any(r in ("tw", "hk", "mo") for r in rest) else "zh-hans"
    if lang == "pt":
        return "pt-br" if "br" in rest else "pt"
    return lang


def source_language(catalog):
    """The language the 'base' or 'default' entries of a catalog are written in: the catalog's source when it names a
    real locale, else English."""
    src = base_locale((catalog or {}).get("source"))
    return src if src and src not in ("base", "default") else "en"
