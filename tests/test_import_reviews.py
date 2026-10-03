"""Tests for src/import_reviews.py — writes only under an explicit temp out-root.

Pinned source text is synthetic (lorem-style Arabic written here), never tafsir.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import export_approved as ea  # noqa: E402
import import_reviews as importer  # noqa: E402

# Synthetic Arabic filler — not from any tafsir or classical source.
SYNTHETIC_SOURCE = (
    "هذا نص تجريبي ملفّق للاختبار فقط. "
    "كلمات متتابعة بلا معنى تراثي: قمرٌ ونهرٌ وكتابٌ وحجرٌ وضوءٌ. "
    "تكرار للتغطية: قمرٌ ونهرٌ وكتابٌ وحجرٌ وضوءٌ مرة أخرى."
)
SYNTH_VERSION = "synthver0001"


def _synth_record(pinned_dir: Path) -> dict:
    pinned_dir.mkdir(parents=True, exist_ok=True)
    source_path = pinned_dir / "1_1.txt"
    raw = SYNTHETIC_SOURCE.encode("utf-8")
    source_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    start, end = 0, 24
    return {
        "annotation_id": "synth_demo-1_1_window-m01",
        "quran": {"surah": 1, "ayah": 1},
        "tafsir": {"id": "synth_demo", "name": "مصدر اختباري ملفّق"},
        "source": {
            "source_id": "synth_demo_1_1",
            "sha256": digest,
            "start_char": start,
            "end_char": end,
        },
        "labels": {"source_method": ["M_TABIIN"], "content_type": []},
        "text": SYNTHETIC_SOURCE[start:end],
        "verification": {
            "text_fidelity": "exact",
            "strict_match": True,
            "normalized_match": True,
        },
        "ai_proposal": {
            "start_char": start,
            "end_char": end,
            "labels": {"source_method": ["M_TABIIN"], "content_type": []},
            "certainty": "explicit",
            "score": 100,
            "route": "auto_candidate",
        },
        "review": {
            "status": "approved",
            "reviewer_role": "tafsir_specialist",
            "reviewed_at": "2026-09-28T12:00:00Z",
            "changes": [],
        },
    }


def _build_synthetic_export(pinned_dir: Path) -> tuple[Path, dict]:
    """Write a temp pinned file + UI export record that matches it letter-for-letter."""
    record = _synth_record(pinned_dir)
    export_path = pinned_dir / "ui_export.json"
    export_path.write_bytes(
        json.dumps({"annotations": [record]}, ensure_ascii=False, indent=2).encode("utf-8")
        + b"\n"
    )
    return export_path, record


class TestImportReviews(unittest.TestCase):
    def test_window_key_from_annotation_id(self) -> None:
        self.assertEqual(
            importer.window_key_for({"annotation_id": "ibn_kathir-2_255_tafsir-m20"}),
            "2_255_tafsir",
        )
        self.assertEqual(
            importer.window_key_for({"annotation_id": "al_tabari-2_255-m07"}),
            "2_255",
        )

    def test_writes_reviews_under_temp_out_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pinned_dir = tmp_path / "pinned"
            export_path, _ = _build_synthetic_export(pinned_dir)
            out_root = tmp_path / "out"
            with mock.patch.dict(
                ea.TAFSIR_SOURCE_DIRS,
                {"synth_demo": pinned_dir, "default": pinned_dir},
                clear=False,
            ):
                report = importer.import_reviews(
                    export_path,
                    base="data/v2",
                    reviewer="fixture_reviewer",
                    out_root=out_root,
                )
            self.assertEqual(report["kept"], 1)
            self.assertEqual(report["dropped_schema"], 0)
            self.assertEqual(report["dropped_fidelity"], 0)
            path = (
                out_root
                / "data"
                / "v2"
                / "reviews"
                / "fixture_reviewer"
                / "1_1_window.json"
            )
            self.assertTrue(path.is_file(), msg=f"missing {path}")
            payload = json.loads(path.read_bytes().decode("utf-8"))
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["review"]["status"], "approved")
            self.assertFalse((ROOT / "data" / "v2" / "reviews").exists())

    def test_out_root_required(self) -> None:
        with self.assertRaises(ValueError):
            importer.import_reviews(
                Path("unused.json"),
                base="data/v2",
                reviewer="x",
                out_root=None,  # type: ignore[arg-type]
            )

    def test_skips_non_approved_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pinned_dir = tmp_path / "pinned"
            export_path, record = _build_synthetic_export(pinned_dir)
            record["review"]["status"] = "ai_proposed"
            src = tmp_path / "in.json"
            src.write_bytes(
                json.dumps({"annotations": [record]}, ensure_ascii=False).encode("utf-8")
            )
            out_root = tmp_path / "out"
            with mock.patch.dict(
                ea.TAFSIR_SOURCE_DIRS,
                {"synth_demo": pinned_dir, "default": pinned_dir},
                clear=False,
            ):
                report = importer.import_reviews(
                    src,
                    base="data/v2",
                    reviewer="fixture_reviewer",
                    out_root=out_root,
                )
            self.assertEqual(report["kept"], 0)
            self.assertEqual(report["skipped"], 1)
            self.assertEqual(report["written_paths"], [])

    def test_records_envelope_matching_version_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pinned_dir = tmp_path / "pinned"
            record = _synth_record(pinned_dir)
            src = tmp_path / "ui.json"
            src.write_bytes(
                json.dumps(
                    {"data_version": SYNTH_VERSION, "records": [record]},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            out_root = tmp_path / "out"
            with mock.patch.dict(
                ea.TAFSIR_SOURCE_DIRS,
                {"synth_demo": pinned_dir, "default": pinned_dir},
                clear=False,
            ), mock.patch.object(ea, "current_data_version", return_value=SYNTH_VERSION):
                report = importer.import_reviews(
                    src,
                    base="data/v2",
                    reviewer="fixture_reviewer",
                    out_root=out_root,
                )
            self.assertEqual(report["kept"], 1)
            self.assertEqual(len(report["written_paths"]), 1)

    def test_records_envelope_version_mismatch_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pinned_dir = tmp_path / "pinned"
            record = _synth_record(pinned_dir)
            src = tmp_path / "ui.json"
            src.write_bytes(
                json.dumps(
                    {"data_version": "wrongversion1", "records": [record]},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            out_root = tmp_path / "out"
            with mock.patch.object(ea, "current_data_version", return_value=SYNTH_VERSION):
                with self.assertRaises(ea.VersionMismatchError) as ctx:
                    importer.import_reviews(
                        src,
                        base="data/v2",
                        reviewer="fixture_reviewer",
                        out_root=out_root,
                    )
            self.assertEqual(str(ctx.exception), ea.VERSION_MISMATCH_MSG)
            self.assertFalse((out_root / "data").exists())

    def test_records_envelope_empty_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "ui.json"
            src.write_bytes(
                json.dumps(
                    {"data_version": SYNTH_VERSION, "records": []},
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            out_root = tmp_path / "out"
            with mock.patch.object(ea, "current_data_version", return_value=SYNTH_VERSION):
                code = importer.main(
                    [
                        str(src),
                        "--base",
                        "data/v2",
                        "--reviewer",
                        "fixture_reviewer",
                        "--out-root",
                        str(out_root),
                    ]
                )
            self.assertEqual(code, 0, msg="empty records → exit 0")
            self.assertEqual(list(out_root.rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
