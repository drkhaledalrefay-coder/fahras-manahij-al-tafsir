"""Build analysis windows for multi-tafsir AUTHOR spans (no re-cutting)."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import read_exact as _read_exact, read_json as _read_json, sha256_file as _sha256_file

from v2_windows import _match_norm, select_2_255_tafsir  # noqa: E402

OUT_ROOT = ROOT / "data" / "multi"
TAFSIR_IDS = ("al_tabari", "al_saadi", "al_baghawi")

_NEEDLE_SINA = "لا تاخذه سنه"
_NEEDLE_HARUT = "هاروت"








def _apparatus_in_range(layers: dict, win_start: int, win_end: int, source: str) -> list[dict]:
    out: list[dict] = []
    for r in layers["ranges"]:
        if r.get("kind") != "apparatus":
            continue
        if r["end"] <= win_start or r["start"] >= win_end:
            continue
        out.append(
            {
                "start": r["start"],
                "end": r["end"],
                "kind": "apparatus",
                "subtype": r.get("subtype"),
                "text": source[r["start"] : r["end"]],
            }
        )
    return out


def _has_phrase_by_phrase_kursi(spans: list[dict]) -> bool:
    for s in spans:
        if _NEEDLE_SINA in _match_norm(s["text"]):
            return True
    return False


def select_2_255(spans: list[dict]) -> tuple[list[dict], dict]:
    if _has_phrase_by_phrase_kursi(spans):
        try:
            window, meta = select_2_255_tafsir(spans)
            meta = dict(meta)
            meta["char_length"] = window[-1]["end"] - window[0]["start"] if window else 0
            return window, meta
        except SystemExit:
            # Anchor pair not found; fall through to capped all-spans.
            pass
    cap = min(len(spans), 110)
    window = list(spans[:cap])
    meta = {
        "rule": "all_spans_capped_110",
        "start_span_id": window[0]["id"] if window else None,
        "end_span_id": window[-1]["id"] if window else None,
        "start_index": 0,
        "end_index": cap - 1 if cap else None,
        "capped_at_110": len(spans) > 110,
        "char_length": window[-1]["end"] - window[0]["start"] if window else 0,
    }
    return window, meta


def select_2_102(spans: list[dict]) -> tuple[list[dict], dict]:
    start_idx = None
    for i, s in enumerate(spans):
        if _NEEDLE_HARUT in _match_norm(s["text"]):
            start_idx = i
            break
    if start_idx is None:
        raise SystemExit("2_102: no span mentioning هاروت (normalized)")
    end_idx = min(len(spans), start_idx + 40) - 1
    window = spans[start_idx : end_idx + 1]
    meta = {
        "rule": "first_harut_cap_40",
        "start_span_id": spans[start_idx]["id"],
        "end_span_id": spans[end_idx]["id"],
        "start_index": start_idx,
        "end_index": end_idx,
        "capped_at_40": True,
        "needle": "هاروت",
        "char_length": window[-1]["end"] - window[0]["start"] if window else 0,
    }
    return window, meta


def select_17_105(spans: list[dict]) -> tuple[list[dict], dict]:
    window = list(spans)
    meta = {
        "rule": "all_spans",
        "start_span_id": window[0]["id"] if window else None,
        "end_span_id": window[-1]["id"] if window else None,
        "char_length": window[-1]["end"] - window[0]["start"] if window else 0,
    }
    return window, meta


def _emit_window(
    tafsir_id: str,
    window_id: str,
    ayah_key: str,
    source_payload: dict,
    spans: list[dict],
    selection: dict,
) -> dict:
    src_path = ROOT / source_payload["source_file"]
    source = _read_exact(src_path)
    layers = _read_json(OUT_ROOT / tafsir_id / "layers" / f"{ayah_key}.json")

    for s in spans:
        assert source[s["start"] : s["end"]] == s["text"], (
            f"{tafsir_id}/{window_id} verbatim fail {s['id']}"
        )

    if not spans:
        raise SystemExit(f"{tafsir_id}/{window_id}: empty window")

    win_start = spans[0]["start"]
    win_end = spans[-1]["end"]
    char_length = win_end - win_start
    selection = dict(selection)
    selection["char_length"] = char_length

    apparatus = _apparatus_in_range(layers, win_start, win_end, source)

    payload = {
        "window_id": window_id,
        "tafsir_id": tafsir_id,
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
    out_dir = OUT_ROOT / tafsir_id / "windows"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{window_id}.json"
    out.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    print(
        f"{tafsir_id}/{window_id}: rule={selection.get('rule')} "
        f"spans={len(spans)} chars={char_length} apparatus={len(apparatus)}"
    )
    return payload


def build_windows() -> dict:
    summary: dict = {}
    selectors = {
        "2_255": ("2_255", select_2_255),
        "2_102": ("2_102", select_2_102),
        "17_105": ("17_105", select_17_105),
    }
    for tafsir_id in TAFSIR_IDS:
        summary[tafsir_id] = {}
        for window_id, (ayah_key, selector) in selectors.items():
            spans_path = OUT_ROOT / tafsir_id / "spans" / f"{ayah_key}.json"
            src = _read_json(spans_path)
            window, meta = selector(src["spans"])
            summary[tafsir_id][window_id] = _emit_window(
                tafsir_id, window_id, ayah_key, src, window, meta
            )
    return summary


if __name__ == "__main__":
    build_windows()
