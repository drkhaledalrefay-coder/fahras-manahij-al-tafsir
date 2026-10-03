"""Unit tests for src/textcore.py (audit phase 2.1)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import (  # noqa: E402
    IntegrityError,
    assert_tiling,
    read_exact,
    read_json,
    resolve_base,
    sha256_bytes,
    sha256_file,
)


class TestReadExact(unittest.TestCase):
    def test_reads_utf8_bytes_without_newline_translation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.txt"
            path.write_bytes("أ\r\nب".encode("utf-8"))
            self.assertEqual(read_exact(path), "أ\r\nب")


class TestReadJson(unittest.TestCase):
    def test_loads_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_bytes(json.dumps({"a": 1, "ب": [2]}, ensure_ascii=False).encode("utf-8"))
            self.assertEqual(read_json(path), {"a": 1, "ب": [2]})


class TestSha256(unittest.TestCase):
    def test_sha256_bytes(self) -> None:
        self.assertEqual(
            sha256_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_sha256_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.bin"
            path.write_bytes(b"abc")
            self.assertEqual(sha256_file(path), sha256_bytes(b"abc"))


class TestAssertTiling(unittest.TestCase):
    def test_ok_full_cover(self) -> None:
        assert_tiling(
            [{"start": 0, "end": 3}, {"start": 3, "end": 5}],
            5,
        )

    def test_ok_empty_text(self) -> None:
        assert_tiling([], 0)

    def test_rejects_unsorted(self) -> None:
        with self.assertRaises(IntegrityError):
            assert_tiling([{"start": 2, "end": 4}, {"start": 0, "end": 2}], 4)

    def test_rejects_gap(self) -> None:
        with self.assertRaises(IntegrityError):
            assert_tiling([{"start": 0, "end": 2}, {"start": 3, "end": 5}], 5)

    def test_rejects_empty_range(self) -> None:
        with self.assertRaises(IntegrityError):
            assert_tiling([{"start": 0, "end": 0}, {"start": 0, "end": 3}], 3)

    def test_rejects_short_cover(self) -> None:
        with self.assertRaises(IntegrityError):
            assert_tiling([{"start": 0, "end": 2}], 5)

    def test_rejects_nonempty_ranges_for_empty_text(self) -> None:
        with self.assertRaises(IntegrityError):
            assert_tiling([{"start": 0, "end": 1}], 0)


class TestResolveBase(unittest.TestCase):
    def test_relative_to_repo_root(self) -> None:
        got = resolve_base("data/v2")
        self.assertEqual(got, (ROOT / "data" / "v2").resolve())

    def test_absolute_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            abs_path = Path(tmp).resolve()
            self.assertEqual(resolve_base(abs_path), abs_path)

    def test_custom_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "base").mkdir()
            self.assertEqual(resolve_base("base", root=root), (root / "base").resolve())


if __name__ == "__main__":
    unittest.main()
