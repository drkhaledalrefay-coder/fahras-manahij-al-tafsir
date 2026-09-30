"""Atomic spans from AUTHOR-layer ranges for multi-tafsir extracts.

Reuses segment_author_chunk from spans_author; does not modify Ibn Kathir outputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from multi_layers import author_text_from_ranges  # noqa: E402
from spans_author import segment_author_chunk  # noqa: E402

RAW_MULTI = ROOT / "data" / "raw" / "tafsircenter"
OUT_ROOT = ROOT / "data" / "multi"

TAFSIR_IDS = ("al_tabari", "al_saadi", "al_baghawi")
TARGET_AYAT = [(2, 255), (2, 102), (17, 105)]


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _span_inside_author(start: int, end: int, author_ranges: list[tuple[int, int]]) -> bool:
    for a, b in author_ranges:
        if a <= start and end <= b:
            return True
    return False


def build_spans() -> dict:
    summary: dict = {}
    for tafsir_id in TAFSIR_IDS:
        summary[tafsir_id] = {}
        spans_dir = OUT_ROOT / tafsir_id / "spans"
        spans_dir.mkdir(parents=True, exist_ok=True)
        for surah, ayah in TARGET_AYAT:
            key = f"{surah}_{ayah}"
            src = RAW_MULTI / tafsir_id / f"{key}.txt"
            layers_path = OUT_ROOT / tafsir_id / "layers" / f"{key}.json"
            if not src.is_file():
                raise SystemExit(f"Missing raw file: {src}")
            if not layers_path.is_file():
                raise SystemExit(f"Missing layers file: {layers_path}")

            text = _read_exact(src)
            layers = json.loads(layers_path.read_bytes().decode("utf-8"))
            ranges = layers["ranges"]
            author_ranges = [(r["start"], r["end"]) for r in ranges if r["kind"] == "author"]
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
                assert text[s["start"] : s["end"]] == s["text"], (
                    f"{tafsir_id}/{key} offset mismatch {s['id']}"
                )
                assert _span_inside_author(s["start"], s["end"], author_ranges), (
                    f"{tafsir_id}/{key} span {s['id']} crosses non-author"
                )

            joined = "".join(s["text"] for s in spans)
            assert joined == author_text, f"{tafsir_id}/{key} author rejoin invariant failed"

            payload = {
                "source": "tafsircenter",
                "tafsir_id": tafsir_id,
                "source_file": str(src.relative_to(ROOT)).replace("\\", "/"),
                "ayah": f"{surah}:{ayah}",
                "surah": surah,
                "ayah_number": ayah,
                "source_char_length": len(text),
                "author_char_length": len(author_text),
                "span_count": len(spans),
                "spans": spans,
            }
            out = spans_dir / f"{key}.json"
            out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
            summary[tafsir_id][key] = len(spans)
            print(
                f"{tafsir_id}/{key}: {len(spans)} author spans "
                f"({len(author_text)} author chars / {len(text)} raw)"
            )
    return summary


if __name__ == "__main__":
    build_spans()
