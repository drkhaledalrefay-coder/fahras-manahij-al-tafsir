"""Gate: layer tiling, spans_author offsets/author-containment, spans_pilot subset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_A = ROOT / "data" / "raw" / "tafsircenter"
LAYERS_DIR = ROOT / "data" / "layers"
SPANS_AUTHOR_DIR = ROOT / "data" / "spans_author"
SPANS_PILOT_DIR = ROOT / "data" / "spans_pilot"
KEYS = ["2_255", "17_105", "2_102"]


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _load(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _assert_tiling(ranges: list[dict], n: int) -> None:
    assert ranges == sorted(ranges, key=lambda r: r["start"]), "not sorted"
    if n == 0:
        assert ranges == []
        return
    assert ranges[0]["start"] == 0
    assert ranges[-1]["end"] == n
    prev_end = 0
    for r in ranges:
        assert r["start"] == prev_end, f"gap/overlap at {prev_end}"
        assert r["end"] > r["start"]
        prev_end = r["end"]
    assert prev_end == n


def _author_intervals(ranges: list[dict]) -> list[tuple[int, int]]:
    return [(r["start"], r["end"]) for r in ranges if r["layer"] == "author"]


def _inside_author(start: int, end: int, intervals: list[tuple[int, int]]) -> bool:
    return any(a <= start and end <= b for a, b in intervals)


def main() -> int:
    ok = True
    for key in KEYS:
        src_text = _read_exact(RAW_A / f"{key}.txt")
        layers = _load(LAYERS_DIR / f"{key}.json")
        spans_a = _load(SPANS_AUTHOR_DIR / f"{key}.json")
        pilot = _load(SPANS_PILOT_DIR / f"{key}.json")

        try:
            _assert_tiling(layers["ranges"], len(src_text))
            tile_ok = True
        except AssertionError as exc:
            tile_ok = False
            ok = False
            print(f"{key}: TILE_FAIL {exc}")
        else:
            print(f"{key}: tile_ok=True ranges={len(layers['ranges'])}")

        author_iv = _author_intervals(layers["ranges"])
        author_text = "".join(src_text[a:b] for a, b in author_iv)
        offset_ok = True
        inside_ok = True
        for s in spans_a["spans"]:
            if src_text[s["start"] : s["end"]] != s["text"]:
                offset_ok = False
                ok = False
            if not _inside_author(s["start"], s["end"], author_iv):
                inside_ok = False
                ok = False
        rejoin_ok = "".join(s["text"] for s in spans_a["spans"]) == author_text
        if not rejoin_ok:
            ok = False
        print(
            f"{key}: spans_author={len(spans_a['spans'])} "
            f"offsets={offset_ok} inside_author={inside_ok} rejoin={rejoin_ok}"
        )

        author_by_id = {s["id"]: s for s in spans_a["spans"]}
        subset_ok = True
        for s in pilot["spans"]:
            parent = author_by_id.get(s["id"])
            if parent is None or parent != s:
                subset_ok = False
                ok = False
                break
        print(
            f"{key}: spans_pilot={len(pilot['spans'])} "
            f"subset_of_spans_author={subset_ok} tile={tile_ok}"
        )

    print("ALL_OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
