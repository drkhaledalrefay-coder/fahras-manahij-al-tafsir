"""Build v2 analysis windows from existing AUTHOR-layer spans (no re-cutting)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from normalize import collapse_whitespace, remove_tashkeel  # noqa: E402

SPANS_AUTHOR_DIR = ROOT / "data" / "spans_author"
SPANS_PILOT_DIR = ROOT / "data" / "spans_pilot"
LAYERS_DIR = ROOT / "data" / "layers"
RAW_A = ROOT / "data" / "raw" / "tafsircenter"
OUT_DIR = ROOT / "data" / "v2" / "windows"

_EDITOR_LAYERS = ("footnote", "verse_ref", "editor_bracket")

# Search needles (tashkeel stripped; ta-marbuta folded to ha for matching only).
# After _match_norm (tashkeel strip + أ→ا + ة→ه): لا تاخذه سنه
_NEEDLE_SINA = "لا تاخذه سنه"
_NEEDLE_WAQULUHU = "وقوله"
_NEEDLE_ALIYY = "العلي العظيم"


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _match_norm(text: str) -> str:
    """Normalize for window search: strip tashkeel, fold ة→ه and alif variants."""
    t = remove_tashkeel(text)
    t = t.replace("\u0629", "\u0647")  # ة → ه (search only; source text untouched)
    for src, dst in (
        ("\u0623", "\u0627"),  # أ → ا
        ("\u0625", "\u0627"),  # إ → ا
        ("\u0622", "\u0627"),  # آ → ا
    ):
        t = t.replace(src, dst)
    return collapse_whitespace(t)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apparatus_in_range(layers: dict, win_start: int, win_end: int, source: str) -> list[dict]:
    out: list[dict] = []
    for r in layers["ranges"]:
        if r["layer"] not in _EDITOR_LAYERS:
            continue
        # Inclusive overlap with [win_start, win_end)
        if r["end"] <= win_start or r["start"] >= win_end:
            continue
        out.append(
            {
                "start": r["start"],
                "end": r["end"],
                "layer": r["layer"],
                "text": source[r["start"] : r["end"]],
            }
        )
    return out


def _emit_window(
    window_id: str,
    ayah_key: str,
    source_payload: dict,
    spans: list[dict],
    selection: dict,
) -> dict:
    src_path = ROOT / source_payload["source_file"]
    source = _read_exact(src_path)
    layers = _read_json(LAYERS_DIR / f"{ayah_key}.json")

    for s in spans:
        assert source[s["start"] : s["end"]] == s["text"], (
            f"{window_id} verbatim fail {s['id']}"
        )

    win_start = spans[0]["start"]
    win_end = spans[-1]["end"]
    apparatus = _apparatus_in_range(layers, win_start, win_end, source)

    payload = {
        "window_id": window_id,
        "ayah": source_payload["ayah"],
        "surah": source_payload["surah"],
        "ayah_number": source_payload["ayah_number"],
        "source": "tafsircenter",
        "source_file": source_payload["source_file"],
        "source_sha256": _sha256_file(src_path),
        "window_start": win_start,
        "window_end": win_end,
        "window_text": source[win_start:win_end],
        "span_count": len(spans),
        "spans": [
            {"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]}
            for s in spans
        ],
        "apparatus": apparatus,
        "selection": selection,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{window_id}.json"
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    first80 = spans[0]["text"][:80]
    last80 = spans[-1]["text"][-80:] if len(spans[-1]["text"]) > 80 else spans[-1]["text"]
    print(
        f"{window_id}: spans={len(spans)} {spans[0]['id']}..{spans[-1]['id']} "
        f"chars={win_end - win_start} apparatus={len(apparatus)}"
    )
    print(f"  first80: {first80!r}")
    print(f"  last80:  {last80!r}")
    return payload


def select_2_255_tafsir(spans: list[dict]) -> tuple[list[dict], dict]:
    """Phrase-by-phrase commentary on Ayat al-Kursi (not fada'il section)."""
    start_idx = None
    for i, s in enumerate(spans):
        n = _match_norm(s["text"])
        if _NEEDLE_SINA not in n:
            continue
        same = _NEEDLE_WAQULUHU in _match_norm(s["text"])
        prev = i > 0 and _NEEDLE_WAQULUHU in _match_norm(spans[i - 1]["text"])
        if same or prev:
            start_idx = i
            break
    if start_idx is None:
        raise SystemExit("2_255_tafsir: start anchor not found")

    end_idx = None
    limit = min(len(spans), start_idx + 110)
    for j in range(start_idx, limit):
        if _NEEDLE_ALIYY in _match_norm(spans[j]["text"]):
            end_idx = j  # keep updating — last span that finishes this phrase
    if end_idx is None:
        end_idx = limit - 1
        capped = True
    else:
        capped = end_idx >= start_idx + 109

    window = spans[start_idx : end_idx + 1]
    meta = {
        "rule": "phrase_by_phrase_kursi",
        "start_span_id": spans[start_idx]["id"],
        "end_span_id": spans[end_idx]["id"],
        "start_index": start_idx,
        "end_index": end_idx,
        "capped_at_110": capped,
        "needle_start": "لا تأخذه سنه + وقوله (same/prev)",
        "needle_end": "العلي العظيم",
    }
    return window, meta


def build_windows() -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary: dict = {}

    # --- 2_255_tafsir ---
    src = _read_json(SPANS_AUTHOR_DIR / "2_255.json")
    window, meta = select_2_255_tafsir(src["spans"])
    summary["2_255_tafsir"] = _emit_window("2_255_tafsir", "2_255", src, window, meta)

    # --- 17_105: all author spans ---
    src = _read_json(SPANS_AUTHOR_DIR / "17_105.json")
    summary["17_105"] = _emit_window(
        "17_105", "17_105", src, list(src["spans"]), {"rule": "all_spans"}
    )

    # --- 2_102: existing pilot window span ids ---
    pilot = _read_json(SPANS_PILOT_DIR / "2_102.json")
    src = _read_json(SPANS_AUTHOR_DIR / "2_102.json")
    by_id = {s["id"]: s for s in src["spans"]}
    pilot_ids = [s["id"] for s in pilot["spans"]]
    window = []
    for sid in pilot_ids:
        if sid not in by_id:
            raise SystemExit(f"2_102: pilot span {sid} missing from spans_author")
        window.append(by_id[sid])
    summary["2_102"] = _emit_window(
        "2_102",
        "2_102",
        src,
        window,
        {
            "rule": "pilot_span_ids",
            "pilot_file": "data/spans_pilot/2_102.json",
            "first_span_id": pilot_ids[0],
            "last_span_id": pilot_ids[-1],
        },
    )
    return summary


if __name__ == "__main__":
    build_windows()
