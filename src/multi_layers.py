"""Classify multi-tafsir characters into author / layout / apparatus layers.

layout   — formatting markup only (HTML tags); may sit inside a highlight later.
apparatus — editor material: footnotes ¬…¥, verse refs, [asN], other brackets.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from layers import is_verse_ref_content  # noqa: E402

RAW_MULTI = ROOT / "data" / "raw" / "tafsircenter"
OUT_ROOT = ROOT / "data" / "multi"

TAFSIR_IDS = ("al_tabari", "al_saadi", "al_baghawi")
TARGET_AYAT = [(2, 255), (2, 102), (17, 105)]

_FOOTNOTE_OPEN = "\u00ac"  # ¬
_FOOTNOTE_CLOSE = "\u00a5"  # ¥

_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_AS_MARKER_RE = re.compile(r"^as\d+$", re.IGNORECASE)


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def survey_patterns(text: str) -> dict:
    """Count every markup / bracket pattern found in the raw string."""
    html_tags = Counter(_HTML_TAG_RE.findall(text))
    footnote_open = text.count(_FOOTNOTE_OPEN)
    footnote_close = text.count(_FOOTNOTE_CLOSE)
    footnotes_closed = 0
    i = 0
    while i < len(text):
        if text[i] == _FOOTNOTE_OPEN:
            j = text.find(_FOOTNOTE_CLOSE, i + 1)
            if j < 0:
                break
            footnotes_closed += 1
            i = j + 1
        else:
            i += 1

    brackets: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "[":
            j = text.find("]", i + 1)
            if j < 0:
                brackets.append(text[i:] + "⟪UNCLOSED⟫")
                break
            brackets.append(text[i : j + 1])
            i = j + 1
        else:
            i += 1

    bracket_patterns: Counter[str] = Counter()
    as_markers: Counter[str] = Counter()
    verse_refs: Counter[str] = Counter()
    other_brackets: Counter[str] = Counter()
    for b in brackets:
        if b.endswith("⟪UNCLOSED⟫"):
            bracket_patterns["UNCLOSED_BRACKET"] += 1
            other_brackets[b] += 1
            continue
        inner = b[1:-1]
        if _AS_MARKER_RE.match(inner):
            bracket_patterns["[asN]"] += 1
            as_markers[b] += 1
        elif is_verse_ref_content(inner):
            bracket_patterns["verse_ref"] += 1
            verse_refs[b] += 1
        else:
            bracket_patterns["other_bracket"] += 1
            other_brackets[b] += 1

    return {
        "html_tags": dict(html_tags),
        "footnote_open": footnote_open,
        "footnote_close": footnote_close,
        "footnotes_closed": footnotes_closed,
        "bracket_total": len(brackets),
        "bracket_pattern_classes": dict(bracket_patterns),
        "as_markers": dict(as_markers),
        "verse_refs": dict(verse_refs),
        "other_brackets": dict(other_brackets),
    }


def _footnote_mask(text: str) -> list[bool]:
    n = len(text)
    mask = [False] * n
    i = 0
    while i < n:
        if text[i] == _FOOTNOTE_OPEN:
            j = text.find(_FOOTNOTE_CLOSE, i + 1)
            if j < 0:
                for k in range(i, n):
                    mask[k] = True
                break
            for k in range(i, j + 1):
                mask[k] = True
            i = j + 1
        else:
            i += 1
    return mask


def _html_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _HTML_TAG_RE.finditer(text)]


def classify(text: str) -> list[dict]:
    """Return contiguous ranges tiling [0, len(text)).

    Each range: {start, end, kind} and for apparatus also {subtype}.
    kind ∈ {author, layout, apparatus}
    apparatus subtype ∈ {footnote, verse_ref, unknown_marker, editor_bracket}
    """
    n = len(text)
    if n == 0:
        return []

    kinds = ["author"] * n
    subtypes: list[str | None] = [None] * n

    fn = _footnote_mask(text)
    for i, flag in enumerate(fn):
        if flag:
            kinds[i] = "apparatus"
            subtypes[i] = "footnote"

    for a, b in _html_spans(text):
        for k in range(a, b):
            if kinds[k] == "author":
                kinds[k] = "layout"
                subtypes[k] = None

    i = 0
    while i < n:
        if kinds[i] != "author":
            i += 1
            continue
        if text[i] != "[":
            i += 1
            continue
        j = i + 1
        close = None
        while j < n:
            if kinds[j] == "apparatus" and subtypes[j] == "footnote":
                j += 1
                continue
            if text[j] == "]":
                close = j
                break
            j += 1
        if close is None:
            i += 1
            continue
        inner = text[i + 1 : close]
        if _AS_MARKER_RE.match(inner):
            subtype = "unknown_marker"
        elif is_verse_ref_content(inner):
            subtype = "verse_ref"
        else:
            subtype = "editor_bracket"
        for k in range(i, close + 1):
            # Footnotes and layout already classified stay as-is.
            if kinds[k] in ("layout",) or (
                kinds[k] == "apparatus" and subtypes[k] == "footnote"
            ):
                continue
            kinds[k] = "apparatus"
            subtypes[k] = subtype
        i = close + 1

    ranges: list[dict] = []
    start = 0
    cur_kind = kinds[0]
    cur_sub = subtypes[0]
    for idx in range(1, n):
        if kinds[idx] != cur_kind or subtypes[idx] != cur_sub:
            entry = {"start": start, "end": idx, "kind": cur_kind}
            if cur_kind == "apparatus":
                entry["subtype"] = cur_sub
            ranges.append(entry)
            start = idx
            cur_kind = kinds[idx]
            cur_sub = subtypes[idx]
    entry = {"start": start, "end": n, "kind": cur_kind}
    if cur_kind == "apparatus":
        entry["subtype"] = cur_sub
    ranges.append(entry)

    _assert_tiling(ranges, n)
    return ranges


def _assert_tiling(ranges: list[dict], n: int) -> None:
    assert ranges == sorted(ranges, key=lambda r: r["start"])
    if n == 0:
        assert ranges == []
        return
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == n
    for a, b in zip(ranges, ranges[1:]):
        assert a["end"] == b["start"]
        assert a["end"] > a["start"]


def range_stats(ranges: list[dict], text: str) -> dict:
    kind_chars = {"author": 0, "layout": 0, "apparatus": 0}
    kind_counts = {"author": 0, "layout": 0, "apparatus": 0}
    subtype_counts: Counter[str] = Counter()
    subtype_chars: Counter[str] = Counter()
    for r in ranges:
        kind = r["kind"]
        length = r["end"] - r["start"]
        kind_chars[kind] = kind_chars.get(kind, 0) + length
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if kind == "apparatus":
            sub = r.get("subtype") or "unknown"
            subtype_counts[sub] += 1
            subtype_chars[sub] += length
    assert sum(kind_chars.values()) == len(text)
    return {
        "range_counts": kind_counts,
        "char_totals": kind_chars,
        "apparatus_subtype_counts": dict(subtype_counts),
        "apparatus_subtype_chars": dict(subtype_chars),
    }


def author_text_from_ranges(text: str, ranges: list[dict]) -> str:
    return "".join(text[r["start"] : r["end"]] for r in ranges if r["kind"] == "author")


def build_layers() -> dict:
    summary: dict = {"survey": {}, "files": {}}
    for tafsir_id in TAFSIR_IDS:
        summary["survey"][tafsir_id] = {}
        summary["files"][tafsir_id] = {}
        out_dir = OUT_ROOT / tafsir_id / "layers"
        out_dir.mkdir(parents=True, exist_ok=True)
        for surah, ayah in TARGET_AYAT:
            key = f"{surah}_{ayah}"
            src = RAW_MULTI / tafsir_id / f"{key}.txt"
            if not src.is_file():
                raise SystemExit(f"Missing raw file: {src}")
            text = _read_exact(src)
            survey = survey_patterns(text)
            ranges = classify(text)
            stats = range_stats(ranges, text)
            payload = {
                "source": "tafsircenter",
                "tafsir_id": tafsir_id,
                "source_file": str(src.relative_to(ROOT)).replace("\\", "/"),
                "ayah": f"{surah}:{ayah}",
                "surah": surah,
                "ayah_number": ayah,
                "source_char_length": len(text),
                "ranges": ranges,
                "range_counts": stats["range_counts"],
                "char_totals": stats["char_totals"],
                "apparatus_subtype_counts": stats["apparatus_subtype_counts"],
                "apparatus_subtype_chars": stats["apparatus_subtype_chars"],
                "survey": survey,
            }
            out = out_dir / f"{key}.json"
            out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
            summary["survey"][tafsir_id][key] = survey
            summary["files"][tafsir_id][key] = {
                "path": str(out.relative_to(ROOT)).replace("\\", "/"),
                **stats,
            }
            print(
                f"{tafsir_id}/{key}: author={stats['char_totals']['author']} "
                f"layout={stats['char_totals']['layout']} "
                f"apparatus={stats['char_totals']['apparatus']} "
                f"subtypes={stats['apparatus_subtype_counts']}"
            )
            if survey["html_tags"]:
                print(f"  html_tags={survey['html_tags']}")
            if survey["as_markers"]:
                print(f"  as_markers={survey['as_markers']}")
            if survey["bracket_pattern_classes"]:
                print(f"  bracket_classes={survey['bracket_pattern_classes']}")
    return summary


if __name__ == "__main__":
    build_layers()
