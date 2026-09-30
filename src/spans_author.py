"""Atomic spans from AUTHOR-layer ranges only (offsets into original Source A)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from layers import author_text_from_ranges, classify  # noqa: E402
from spans import (  # noqa: E402
    _BREAK_AFTER,
    _MAX_WORDS,
    _MIN_WORDS,
    _in_ranges,
    _marker_starts,
    _merge_short,
    _quranic_ranges,
    _spans_from_breaks,
    _word_count,
)

RAW_A = ROOT / "data" / "raw" / "tafsircenter"
LAYERS_DIR = ROOT / "data" / "layers"
SPANS_AUTHOR_DIR = ROOT / "data" / "spans_author"
TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]

_SURAH_WORD = "\u0633\u0648\u0631\u0629"  # سورة


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _is_digit_char(ch: str) -> bool:
    return ch.isdigit() or "\u0660" <= ch <= "\u0669" or "\u06f0" <= ch <= "\u06f9"


def _colon_followed_by_digits(text: str, colon_idx: int) -> bool:
    """True if ':' at colon_idx is followed (after spaces) by a digit."""
    nxt = colon_idx + 1
    while nxt < len(text) and text[nxt] in " \t":
        nxt += 1
    return nxt < len(text) and _is_digit_char(text[nxt])


def _colon_after_surah_word(text: str, colon_idx: int) -> bool:
    """True if ':' is immediately preceded by سورة (optional spaces already stripped back)."""
    j = colon_idx - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    end = j + 1
    start = end - len(_SURAH_WORD)
    if start < 0:
        return False
    return text[start:end] == _SURAH_WORD


def _should_break_after_char(text: str, i: int, ranges: list[tuple[int, int]]) -> bool:
    """Whether a break may start at i+1 after text[i], with colon safety fixes."""
    ch = text[i]
    if ch not in _BREAK_AFTER:
        return False
    nxt = i + 1
    if nxt >= len(text):
        return False
    if _in_ranges(i, ranges) or _in_ranges(nxt, ranges):
        return False
    if ch == ":":
        if _colon_followed_by_digits(text, i):
            return False
        if _colon_after_surah_word(text, i):
            return False
    return True


def _candidate_breaks_author(text: str) -> list[int]:
    """Same as spans._candidate_breaks, but do not break on verse-style / سورة colons."""
    ranges = _quranic_ranges(text)
    breaks = {0, len(text)}

    for i, ch in enumerate(text):
        if _should_break_after_char(text, i, ranges):
            breaks.add(i + 1)

    for idx in _marker_starts(text):
        if not _in_ranges(idx, ranges):
            breaks.add(idx)

    return sorted(breaks)


def _split_long_author(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Like spans._split_long but respects colon non-break rules."""
    ranges = _quranic_ranges(text)
    out: list[tuple[int, int]] = []
    for a, b in spans:
        chunk = text[a:b]
        if _word_count(chunk) <= _MAX_WORDS:
            out.append((a, b))
            continue
        internal = []
        for i, ch in enumerate(chunk):
            abs_i = a + i
            if ch in _BREAK_AFTER and i + 1 < len(chunk):
                if not _should_break_after_char(text, abs_i, ranges):
                    continue
                left_wc = _word_count(chunk[: i + 1])
                right_wc = _word_count(chunk[i + 1 :])
                if left_wc >= _MIN_WORDS and right_wc >= _MIN_WORDS:
                    internal.append(i + 1)
        if not internal:
            out.append((a, b))
            continue
        cursor = 0
        while cursor < len(chunk):
            remaining = chunk[cursor:]
            if _word_count(remaining) <= _MAX_WORDS:
                out.append((a + cursor, b))
                break
            choice = None
            for br in internal:
                if br <= cursor:
                    continue
                left = chunk[cursor:br]
                wc = _word_count(left)
                if _MIN_WORDS <= wc <= _MAX_WORDS:
                    choice = br
                elif wc > _MAX_WORDS:
                    break
            if choice is None:
                for br in internal:
                    if br > cursor and _word_count(chunk[cursor:br]) >= _MIN_WORDS:
                        choice = br
                        break
            if choice is None:
                out.append((a + cursor, b))
                break
            out.append((a + cursor, a + choice))
            cursor = choice
    return out


def segment_author_chunk(text: str) -> list[tuple[int, int]]:
    """Segment a single contiguous author chunk; returns local [start, end) pairs."""
    if not text:
        return []
    breaks = _candidate_breaks_author(text)
    spans = _spans_from_breaks(text, breaks)
    spans = _merge_short(text, spans)
    spans = _split_long_author(text, spans)
    spans = _merge_short(text, spans)
    return spans


def _load_ranges(key: str, text: str) -> list[dict]:
    path = LAYERS_DIR / f"{key}.json"
    if path.is_file():
        return json.loads(path.read_bytes().decode("utf-8"))["ranges"]
    return classify(text)


def _span_inside_author(start: int, end: int, author_ranges: list[tuple[int, int]]) -> bool:
    for a, b in author_ranges:
        if a <= start and end <= b:
            return True
    return False


def build_spans_author() -> dict:
    SPANS_AUTHOR_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for surah, ayah in TARGET_AYAT:
        key = f"{surah}_{ayah}"
        src = RAW_A / f"{key}.txt"
        text = _read_exact(src)
        ranges = _load_ranges(key, text)
        author_ranges = [(r["start"], r["end"]) for r in ranges if r["layer"] == "author"]
        author_text = author_text_from_ranges(text, ranges)

        spans: list[dict] = []
        for ar_start, ar_end in author_ranges:
            chunk = text[ar_start:ar_end]
            for loc_a, loc_b in segment_author_chunk(chunk):
                start = ar_start + loc_a
                end = ar_start + loc_b
                span_text = text[start:end]
                assert span_text == chunk[loc_a:loc_b]
                spans.append({"start": start, "end": end, "text": span_text})

        for i, s in enumerate(spans, 1):
            s["id"] = f"s{i:03d}"
            assert text[s["start"] : s["end"]] == s["text"], f"{key} offset mismatch {s['id']}"
            assert _span_inside_author(s["start"], s["end"], author_ranges), (
                f"{key} span {s['id']} crosses non-author"
            )

        joined = "".join(s["text"] for s in spans)
        assert joined == author_text, f"{key} author rejoin invariant failed"

        payload = {
            "source": "tafsircenter",
            "source_file": str(src.relative_to(ROOT)).replace("\\", "/"),
            "ayah": f"{surah}:{ayah}",
            "surah": surah,
            "ayah_number": ayah,
            "source_char_length": len(text),
            "author_char_length": len(author_text),
            "span_count": len(spans),
            "spans": spans,
        }
        out = SPANS_AUTHOR_DIR / f"{key}.json"
        out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        summary[key] = len(spans)
        print(f"{key}: {len(spans)} author spans ({len(author_text)} chars)")
    return summary


if __name__ == "__main__":
    build_spans_author()
