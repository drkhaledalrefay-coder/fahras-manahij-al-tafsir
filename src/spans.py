"""Split Source A L0 tafsir text into atomic spans (code-only segmentation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import read_exact as _read_exact

RAW_A = ROOT / "data" / "raw" / "tafsircenter"
SPANS_DIR = ROOT / "data" / "spans"
TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]

# Break after these sentence/clause terminators.
_BREAK_AFTER = set(".؟!:؛\n")

# Structural markers (longest first). Guillemets optional in source text.
# Phrases are structural split cues required by the span algorithm, not pasted tafsir.
_MARKER_PATTERNS = [
    "\u00ab\u062d\u062f\u064a\u062b \u0622\u062e\u0631\u00bb",  # «حديث آخر»
    "\u062d\u062f\u064a\u062b \u0622\u062e\u0631",  # حديث آخر
    "\u00ab\u0637\u0631\u064a\u0642 \u0623\u062e\u0631\u0649\u00bb",  # «طريق أخرى»
    "\u0637\u0631\u064a\u0642 \u0623\u062e\u0631\u0649",  # طريق أخرى
    "\u00ab\u0648\u0642\u0648\u0644\u0647\u00bb",  # «وقوله»
    "\u0648\u0642\u0648\u0644\u0647",  # وقوله
    "\u00ab\u0648\u0642\u0627\u0644\u00bb",  # «وقال»
    "\u0648\u0642\u0627\u0644",  # وقال
    "\u00ab\u0642\u0627\u0644\u00bb",  # «قال»
    "\u0642\u0627\u0644",  # قال
]

_MIN_WORDS = 5
_MAX_WORDS = 60




def _quranic_ranges(text: str) -> list[tuple[int, int]]:
    """Return [start, end) ranges for ﴿...﴾ regions that must not be split."""
    ranges: list[tuple[int, int]] = []
    i = 0
    while True:
        start = text.find("\ufd3f", i)  # ﴿
        if start < 0:
            break
        end = text.find("\ufd3e", start + 1)  # ﴾
        if end < 0:
            break
        ranges.append((start, end + 1))
        i = end + 1
    return ranges


def _in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in ranges)


def _preceded_by_sentence_end(text: str, pos: int) -> bool:
    """True if pos is start-of-text or the nearest non-space before pos is sentence end."""
    j = pos - 1
    while j >= 0 and text[j] in " \t\r":
        j -= 1
    if j < 0:
        return True
    return text[j] in _BREAK_AFTER or text[j] == "\n"


def _marker_starts(text: str) -> list[int]:
    """Positions where a structural marker begins, if preceded by sentence end."""
    starts: list[int] = []
    # Build alternation with longer phrases first; use word-ish boundaries for قال variants.
    for marker in _MARKER_PATTERNS:
        start = 0
        while True:
            idx = text.find(marker, start)
            if idx < 0:
                break
            # Avoid matching قال inside longer words: require non-letter before/after when bare.
            before_ok = idx == 0 or not (text[idx - 1].isalnum() or "\u0600" <= text[idx - 1] <= "\u06ff")
            after_idx = idx + len(marker)
            after_ok = after_idx >= len(text) or not (
                text[after_idx].isalnum() or "\u0600" <= text[after_idx] <= "\u06ff"
            )
            # For multi-word markers, still require after_ok loosely (punctuation/space ok).
            if before_ok and after_ok and _preceded_by_sentence_end(text, idx):
                starts.append(idx)
            start = idx + 1
    return starts


def _candidate_breaks(text: str) -> list[int]:
    """Return sorted unique indices where a new span may start."""
    ranges = _quranic_ranges(text)
    breaks = {0, len(text)}

    for i, ch in enumerate(text):
        if ch in _BREAK_AFTER:
            nxt = i + 1
            if nxt < len(text) and not _in_ranges(i, ranges) and not _in_ranges(nxt, ranges):
                breaks.add(nxt)
        # Treat \r\n: after \r alone do not break; after \n already handled via _BREAK_AFTER.

    for idx in _marker_starts(text):
        if not _in_ranges(idx, ranges):
            breaks.add(idx)

    return sorted(breaks)


def _word_count(s: str) -> int:
    return len(s.split())


def _spans_from_breaks(text: str, breaks: list[int]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for a, b in zip(breaks, breaks[1:]):
        if a < b:
            pairs.append((a, b))
    return pairs


def _merge_short(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge spans shorter than ~5 words into neighbors when possible."""
    if not spans:
        return spans
    spans = list(spans)
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(spans):
            a, b = spans[i]
            wc = _word_count(text[a:b])
            if wc < _MIN_WORDS and len(spans) > 1:
                if i + 1 < len(spans):
                    # merge with next
                    spans[i] = (a, spans[i + 1][1])
                    del spans[i + 1]
                    changed = True
                    continue
                if i > 0:
                    spans[i - 1] = (spans[i - 1][0], b)
                    del spans[i]
                    changed = True
                    continue
            i += 1
    return spans


def _split_long(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Attempt to split spans longer than ~60 words at internal sentence breaks."""
    ranges = _quranic_ranges(text)
    out: list[tuple[int, int]] = []
    for a, b in spans:
        chunk = text[a:b]
        if _word_count(chunk) <= _MAX_WORDS:
            out.append((a, b))
            continue
        # Find internal break-after positions relative to chunk.
        internal = []
        for i, ch in enumerate(chunk):
            abs_i = a + i
            if ch in _BREAK_AFTER and i + 1 < len(chunk):
                if not _in_ranges(abs_i, ranges) and not _in_ranges(abs_i + 1, ranges):
                    # Prefer breaks that leave both sides within soft bounds when possible
                    left_wc = _word_count(chunk[: i + 1])
                    right_wc = _word_count(chunk[i + 1 :])
                    if left_wc >= _MIN_WORDS and right_wc >= _MIN_WORDS:
                        internal.append(i + 1)
        if not internal:
            out.append((a, b))
            continue
        # Greedily cut near max words.
        cursor = 0
        while cursor < len(chunk):
            remaining = chunk[cursor:]
            if _word_count(remaining) <= _MAX_WORDS:
                out.append((a + cursor, b))
                break
            # choose largest internal break that keeps left <= MAX and >= MIN
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
                # fallback: first internal break after cursor with left >= MIN
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


def segment(text: str) -> list[dict]:
    """Segment L0 text into atomic spans with exact rejoin invariant."""
    breaks = _candidate_breaks(text)
    spans = _spans_from_breaks(text, breaks)
    spans = _merge_short(text, spans)
    spans = _split_long(text, spans)
    # Re-merge any shorts introduced by split edge cases
    spans = _merge_short(text, spans)

    result = []
    for i, (start, end) in enumerate(spans, 1):
        result.append(
            {
                "id": f"s{i:03d}",
                "start": start,
                "end": end,
                "text": text[start:end],
            }
        )
    joined = "".join(s["text"] for s in result)
    assert joined == text, "span rejoin invariant failed"
    return result


def build_spans() -> dict:
    SPANS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}
    for surah, ayah in TARGET_AYAT:
        key = f"{surah}_{ayah}"
        src = RAW_A / f"{key}.txt"
        text = _read_exact(src)
        spans = segment(text)
        payload = {
            "source": "tafsircenter",
            "source_file": str(src.relative_to(ROOT)).replace("\\", "/"),
            "ayah": f"{surah}:{ayah}",
            "surah": surah,
            "ayah_number": ayah,
            "source_char_length": len(text),
            "span_count": len(spans),
            "spans": spans,
        }
        out = SPANS_DIR / f"{key}.json"
        out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        # verify invariant again from disk-shaped data
        assert "".join(s["text"] for s in spans) == text
        summary[key] = len(spans)
    return summary


if __name__ == "__main__":
    s = build_spans()
    for k, n in s.items():
        print(f"{k}: {n} spans")
