"""Classify Source A characters into author vs editorial apparatus layers."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

RAW_A = ROOT / "data" / "raw" / "tafsircenter"
LAYERS_DIR = ROOT / "data" / "layers"
TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]

_FOOTNOTE_OPEN = "\u00ac"  # ¬
_FOOTNOTE_CLOSE = "\u00a5"  # ¥

# Verse ref: sura-name + colon + digits (Latin/Arabic-Indic/Eastern), optional ranges.
_DIGIT = r"[0-9\u0660-\u0669\u06f0-\u06f9]"
_VERSE_REF_RE = re.compile(
    rf"^.+:\s*{_DIGIT}+(?:\s*[-–]\s*{_DIGIT}+|\s*[،,]\s*{_DIGIT}+)*\s*$"
)

LAYERS = ("author", "footnote", "verse_ref", "editor_bracket")


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def is_verse_ref_content(inner: str) -> bool:
    """True if bracket inner text looks like a sura:ayah reference."""
    return bool(_VERSE_REF_RE.match(inner))


def _footnote_mask(text: str) -> list[bool]:
    """True where character belongs to a ¬...¥ footnote (inclusive)."""
    n = len(text)
    mask = [False] * n
    i = 0
    while i < n:
        if text[i] == _FOOTNOTE_OPEN:
            j = text.find(_FOOTNOTE_CLOSE, i + 1)
            if j < 0:
                # Unclosed: treat remainder as footnote (defensive).
                for k in range(i, n):
                    mask[k] = True
                break
            for k in range(i, j + 1):
                mask[k] = True
            i = j + 1
        else:
            i += 1
    return mask


def classify(text: str) -> list[dict]:
    """Return contiguous {start, end, layer} ranges tiling [0, len(text))."""
    n = len(text)
    if n == 0:
        return []

    labels = ["author"] * n
    fn = _footnote_mask(text)
    for i, flag in enumerate(fn):
        if flag:
            labels[i] = "footnote"

    i = 0
    while i < n:
        if labels[i] == "footnote":
            i += 1
            continue
        if text[i] == "[":
            j = i + 1
            close = None
            while j < n:
                if labels[j] == "footnote":
                    j += 1
                    continue
                if text[j] == "]":
                    close = j
                    break
                j += 1
            if close is None:
                # Unclosed '[' — leave as author.
                i += 1
                continue
            # Inner text for pattern match: full slice (footnotes inside ⇒ not verse_ref).
            inner = text[i + 1 : close]
            layer = "verse_ref" if is_verse_ref_content(inner) else "editor_bracket"
            for k in range(i, close + 1):
                if labels[k] != "footnote":
                    labels[k] = layer
            i = close + 1
        else:
            i += 1

    ranges: list[dict] = []
    start = 0
    cur = labels[0]
    for idx in range(1, n):
        if labels[idx] != cur:
            ranges.append({"start": start, "end": idx, "layer": cur})
            start = idx
            cur = labels[idx]
    ranges.append({"start": start, "end": n, "layer": cur})

    _assert_tiling(ranges, n)
    return ranges


def _assert_tiling(ranges: list[dict], n: int) -> None:
    assert ranges == sorted(ranges, key=lambda r: r["start"]), "ranges not sorted"
    if n == 0:
        assert ranges == []
        return
    assert ranges[0]["start"] == 0, "ranges do not start at 0"
    assert ranges[-1]["end"] == n, "ranges do not end at len(text)"
    for a, b in zip(ranges, ranges[1:]):
        assert a["end"] == b["start"], f"gap/overlap at {a['end']} vs {b['start']}"
        assert a["end"] > a["start"], "empty range"
    assert ranges[-1]["end"] > ranges[-1]["start"] or n == 0


def layer_stats(ranges: list[dict], text: str) -> dict:
    counts = {layer: 0 for layer in LAYERS}
    chars = {layer: 0 for layer in LAYERS}
    for r in ranges:
        layer = r["layer"]
        counts[layer] = counts.get(layer, 0) + 1
        chars[layer] = chars.get(layer, 0) + (r["end"] - r["start"])
    assert sum(chars.values()) == len(text), "char totals do not cover text"
    return {"range_counts": counts, "char_totals": chars}


def author_text_from_ranges(text: str, ranges: list[dict]) -> str:
    return "".join(text[r["start"] : r["end"]] for r in ranges if r["layer"] == "author")


def build_layers() -> dict:
    LAYERS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for surah, ayah in TARGET_AYAT:
        key = f"{surah}_{ayah}"
        src = RAW_A / f"{key}.txt"
        text = _read_exact(src)
        ranges = classify(text)
        stats = layer_stats(ranges, text)
        payload = {
            "source": "tafsircenter",
            "source_file": str(src.relative_to(ROOT)).replace("\\", "/"),
            "ayah": f"{surah}:{ayah}",
            "surah": surah,
            "ayah_number": ayah,
            "source_char_length": len(text),
            "ranges": ranges,
            "range_counts": stats["range_counts"],
            "char_totals": stats["char_totals"],
        }
        out = LAYERS_DIR / f"{key}.json"
        out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        summary[key] = stats["char_totals"]
        print(
            f"{key}: author={stats['char_totals']['author']} "
            f"footnote={stats['char_totals']['footnote']} "
            f"verse_ref={stats['char_totals']['verse_ref']} "
            f"editor_bracket={stats['char_totals']['editor_bracket']}"
        )
    return summary


if __name__ == "__main__":
    build_layers()
