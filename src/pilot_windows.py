"""Select pilot subsets of author spans for tagging."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

SPANS_AUTHOR_DIR = ROOT / "data" / "spans_author"
SPANS_PILOT_DIR = ROOT / "data" / "spans_pilot"

# Anchor substring for 2:102 window (must be located by code, not hard-coded index).
_ANCHOR_2_102 = (
    "\u0643\u0639\u0628 \u0627\u0644\u0623\u062d\u0628\u0627\u0631 "
    "\u0639\u0646 \u0643\u062a\u0628 \u0628\u0646\u064a \u0625\u0633\u0631\u0627\u0626\u064a\u0644"
)  # كعب الأحبار عن كتب بني إسرائيل


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _window_all(spans: list[dict]) -> list[dict]:
    return list(spans)


def _window_until_chars(spans: list[dict], limit: int) -> list[dict]:
    """Take spans from the start until cumulative text length first exceeds limit."""
    out: list[dict] = []
    cum = 0
    for s in spans:
        out.append(s)
        cum += len(s["text"])
        if cum > limit:
            break
    return out


def _window_around_anchor(spans: list[dict], anchor: str, before: int, after: int) -> tuple[list[dict], dict]:
    """Return window around span containing anchor; metadata describes fallback if needed."""
    hit_idx = None
    for i, s in enumerate(spans):
        if anchor in s["text"]:
            hit_idx = i
            break
    meta = {"anchor": anchor, "found": hit_idx is not None, "anchor_span_index": hit_idx}
    if hit_idx is None:
        meta["fallback"] = "spans_index_380_430_inclusive"
        print(f"WARNING: anchor not found for 2:102; using fallback spans[380:431]")
        return list(spans[380:431]), meta
    start = max(0, hit_idx - before)
    end = min(len(spans), hit_idx + after + 1)
    meta["window_index_start"] = start
    meta["window_index_end_exclusive"] = end
    meta["anchor_span_id"] = spans[hit_idx]["id"]
    return spans[start:end], meta


def _emit(key: str, source_payload: dict, window: list[dict], extra: dict | None = None) -> dict:
    char_count = sum(len(s["text"]) for s in window)
    first_id = window[0]["id"] if window else None
    last_id = window[-1]["id"] if window else None
    payload = {
        "source": source_payload.get("source"),
        "source_file": source_payload.get("source_file"),
        "ayah": source_payload.get("ayah"),
        "surah": source_payload.get("surah"),
        "ayah_number": source_payload.get("ayah_number"),
        "span_count": len(window),
        "char_count": char_count,
        "first_span_id": first_id,
        "last_span_id": last_id,
        "spans": window,
    }
    if extra:
        payload["selection"] = extra
    out = SPANS_PILOT_DIR / f"{key}.json"
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(
        f"{key}: spans={len(window)} chars={char_count} "
        f"first={first_id} last={last_id}"
    )
    return payload


def build_pilot_windows() -> dict:
    SPANS_PILOT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {}

    # 17:105 — all author spans
    key = "17_105"
    src = _read_json(SPANS_AUTHOR_DIR / f"{key}.json")
    window = _window_all(src["spans"])
    summary[key] = _emit(key, src, window, {"rule": "all_spans"})

    # 2:255 — until cumulative length first exceeds 6000
    key = "2_255"
    src = _read_json(SPANS_AUTHOR_DIR / f"{key}.json")
    window = _window_until_chars(src["spans"], 6000)
    cum = sum(len(s["text"]) for s in window)
    summary[key] = _emit(
        key,
        src,
        window,
        {"rule": "cumulative_chars_exceeds", "threshold": 6000, "cumulative_chars": cum},
    )

    # 2:102 — around anchor substring
    key = "2_102"
    src = _read_json(SPANS_AUTHOR_DIR / f"{key}.json")
    window, meta = _window_around_anchor(src["spans"], _ANCHOR_2_102, before=20, after=10)
    meta["rule"] = "anchor_minus_20_plus_10"
    summary[key] = _emit(key, src, window, meta)

    return summary


if __name__ == "__main__":
    build_pilot_windows()
