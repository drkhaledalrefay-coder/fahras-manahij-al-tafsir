"""Integrity gates formerly run as src/check_phase1b.py and src/check_spans_rejoin.py."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import IntegrityError, assert_tiling, read_exact, read_json  # noqa: E402

RAW_A = ROOT / "data" / "raw" / "tafsircenter"
LAYERS_DIR = ROOT / "data" / "layers"
SPANS_AUTHOR_DIR = ROOT / "data" / "spans_author"
SPANS_PILOT_DIR = ROOT / "data" / "spans_pilot"
SPANS_DIR = ROOT / "data" / "spans"
KEYS = ["2_255", "17_105", "2_102"]


def _author_intervals(ranges: list[dict]) -> list[tuple[int, int]]:
    return [(r["start"], r["end"]) for r in ranges if r["layer"] == "author"]


def _inside_author(start: int, end: int, intervals: list[tuple[int, int]]) -> bool:
    return any(a <= start and end <= b for a, b in intervals)


class TestPhase1bIntegrity(unittest.TestCase):
    """Layer tiling, spans_author offsets/containment, pilot ⊂ author."""

    def test_tiling_offsets_pilot_subset(self) -> None:
        for key in KEYS:
            with self.subTest(key=key):
                src_text = read_exact(RAW_A / f"{key}.txt")
                layers = read_json(LAYERS_DIR / f"{key}.json")
                spans_a = read_json(SPANS_AUTHOR_DIR / f"{key}.json")
                pilot = read_json(SPANS_PILOT_DIR / f"{key}.json")

                try:
                    assert_tiling(layers["ranges"], len(src_text))
                except IntegrityError as exc:
                    self.fail(f"{key}: tiling failed: {exc}")

                author_iv = _author_intervals(layers["ranges"])
                author_text = "".join(src_text[a:b] for a, b in author_iv)
                for s in spans_a["spans"]:
                    self.assertEqual(
                        src_text[s["start"] : s["end"]],
                        s["text"],
                        f"{key}: span offset mismatch {s.get('id')}",
                    )
                    self.assertTrue(
                        _inside_author(s["start"], s["end"], author_iv),
                        f"{key}: span outside author layer {s.get('id')}",
                    )
                self.assertEqual(
                    "".join(s["text"] for s in spans_a["spans"]),
                    author_text,
                    f"{key}: spans_author does not rejoin author text",
                )

                author_by_id = {s["id"]: s for s in spans_a["spans"]}
                for s in pilot["spans"]:
                    parent = author_by_id.get(s["id"])
                    self.assertIsNotNone(parent, f"{key}: pilot id missing in author {s.get('id')}")
                    self.assertEqual(parent, s, f"{key}: pilot span != author span {s.get('id')}")


class TestSpansRejoin(unittest.TestCase):
    """Every data/spans/*.json rejoins its Source A file byte-for-byte."""

    def test_spans_rejoin_source_a(self) -> None:
        span_files = sorted(SPANS_DIR.glob("*.json"))
        self.assertTrue(span_files, "expected pinned span files under data/spans/")
        for span_path in span_files:
            with self.subTest(key=span_path.stem):
                payload = read_json(span_path)
                key = span_path.stem
                src = RAW_A / f"{key}.txt"
                src_bytes = src.read_bytes()
                src_text = src_bytes.decode("utf-8")
                joined = "".join(s["text"] for s in payload["spans"])
                self.assertEqual(joined, src_text, f"{key}: rejoin text mismatch")
                self.assertEqual(joined.encode("utf-8"), src_bytes, f"{key}: rejoin bytes mismatch")
                for s in payload["spans"]:
                    self.assertEqual(
                        src_text[s["start"] : s["end"]],
                        s["text"],
                        f"{key}: offset mismatch {s.get('id')}",
                    )
                # Keep sha visible in failure context if someone debugs manually.
                self.assertEqual(len(hashlib.sha256(src_bytes).hexdigest()), 64)


if __name__ == "__main__":
    unittest.main()
