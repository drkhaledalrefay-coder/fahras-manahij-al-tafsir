"""Tests for src/export_approved.py.

The four-record UI-export sample is built at runtime from
schema/example_approved.json (not stored under tests/fixtures): one approved and
faithful record, the same record still ai_proposed, the same span with one letter
changed in text, and the same span plus an unknown field. Only the first may reach
approved.json.

Run with pytest, or with:
    python -m unittest discover -s tests -p "test_export_approved.py"
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import export_approved as exporter  # noqa: E402

# Synthetic Arabic filler — not from any tafsir (PART 4 envelope tests).
SYNTHETIC_SOURCE = (
    "هذا نص تجريبي ملفّق للاختبار فقط. "
    "كلمات متتابعة بلا معنى تراثي: قمرٌ ونهرٌ وكتابٌ وحجرٌ وضوءٌ."
)
SYNTH_VERSION = "synthver0001"

EXAMPLE = ROOT / "schema" / "example_approved.json"
RAW_DIR = ROOT / "data" / "raw" / "tafsircenter"
EXAMPLE_ID = "ibn_kathir-2_255_tafsir-m20"
SCHEMA_LINE = "المرفوض بسبب المخطط"
FIDELITY_LINE = "المرفوض بسبب عدم المطابقة"


def read_json(path: Path):
    return json.loads(Path(path).read_bytes().decode("utf-8"))


def ui_export_sample() -> list[dict]:
    """Runtime stand-in for a UI export: no tafsir text stored under tests/fixtures."""
    valid = read_json(EXAMPLE)
    pending = copy.deepcopy(valid)
    pending["review"] = {
        "status": "ai_proposed",
        "reviewer_role": "tafsir_specialist",
        "reviewed_at": "2026-09-28T12:00:00Z",
        "changes": [],
    }
    changed = copy.deepcopy(valid)
    changed["annotation_id"] = "ibn_kathir-2_255_tafsir-m21"
    # One-letter corruption for fidelity failure (last letter of the slice).
    text = changed["text"]
    changed["text"] = text[:-2] + ("ز" if text[-2] != "ز" else "س") + text[-1:]
    unknown = copy.deepcopy(valid)
    unknown["annotation_id"] = "ibn_kathir-2_255_tafsir-m22"
    unknown["ui_note"] = "should fail schema"
    return [valid, pending, changed, unknown]


def record_for(
    surah: int,
    ayah: int,
    start: int,
    length: int,
    annotation_id: str,
    status: str = "approved",
    reviewed_at: str = "2026-09-28T12:00:00Z",
) -> dict:
    """A genuinely valid record, sliced straight from the pinned source file."""
    raw = (RAW_DIR / f"{surah}_{ayah}.txt").read_bytes()
    text = raw.decode("utf-8")[start : start + length]
    assert text, "empty slice"
    return {
        "annotation_id": annotation_id,
        "quran": {"surah": surah, "ayah": ayah},
        "tafsir": {"id": "ibn_kathir", "name": "تفسير ابن كثير"},
        "source": {
            "source_id": f"ibn_kathir_{surah}_{ayah}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "start_char": start,
            "end_char": start + length,
        },
        "labels": {"source_method": ["M_TABIIN"], "content_type": []},
        "text": text,
        "verification": {"text_fidelity": "exact", "strict_match": True, "normalized_match": True},
        "ai_proposal": {
            "start_char": start,
            "end_char": start + length,
            "labels": {"source_method": [], "content_type": []},
            "certainty": "insufficient",
            "score": 0,
            "route": "specialist",
        },
        "review": {
            "status": status,
            "reviewer_role": "tafsir_specialist",
            "reviewed_at": reviewed_at,
            "changes": [],
        },
    }


class ExportApprovedTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        # Nested on purpose: the tool must create the output directory itself.
        self.out = self.workspace / "nested" / "approved.json"

    def write_input(self, payload, name: str = "input.json") -> Path:
        path = self.workspace / name
        path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
        return path

    def run_main(self, payload, *extra: str):
        path = self.write_input(payload)
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = exporter.main([str(path), "--out", str(self.out), *extra])
        return code, buffer.getvalue()

    def report(self, payload, *extra: str) -> dict:
        return exporter.export(
            self.write_input(payload),
            self.out,
            include_rejected="--include-rejected" in extra,
        )

    # --- the fixture itself -------------------------------------------------------

    def test_fixture_holds_the_four_intended_records(self):
        payload = ui_export_sample()
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 4)
        valid, pending, changed, unknown = payload
        example = read_json(EXAMPLE)
        self.assertEqual(valid, example)
        self.assertEqual(exporter.review_status(pending), "ai_proposed")
        self.assertEqual(exporter.review_status(changed), "approved")
        self.assertEqual(exporter.review_status(unknown), "approved")
        self.assertEqual(pending["annotation_id"], example["annotation_id"])
        # (c) keeps the same length but differs in exactly one letter
        self.assertEqual(len(changed["text"]), len(example["text"]))
        self.assertEqual(
            sum(1 for a, b in zip(changed["text"], example["text"]) if a != b),
            1,
        )
        # (d) adds exactly one unknown top-level field
        self.assertEqual(set(unknown) - set(example), {"ui_note"})
        self.assertEqual(set(changed), set(example))

    def test_fixture_writes_only_the_valid_record(self):
        code, summary = self.run_main(ui_export_sample())
        self.assertEqual(code, 1)
        self.assertEqual(read_json(self.out), [read_json(EXAMPLE)])
        for line in (
            "عدد المدخل: 4",
            "المعتمد المكتوب: 1",
            f"{SCHEMA_LINE}: 1",
            f"{FIDELITY_LINE}: 1",
            "المكرر: 0",
            "غير معتمد (لم يُفحص ولم يُكتب): 1",
            "تفاصيل المرفوض:",
        ):
            self.assertIn(line, summary)

    def test_fixture_report_counts_and_reasons(self):
        report = self.report(ui_export_sample())
        self.assertEqual(
            (
                report["input"],
                report["selected"],
                report["skipped"],
                report["written"],
                report["dropped_schema"],
                report["dropped_fidelity"],
                report["duplicates"],
            ),
            (4, 3, 1, 1, 1, 1, 0),
        )
        self.assertEqual(report["written_ids"], [EXAMPLE_ID])
        stages = {entry["annotation_id"]: entry["stage"] for entry in report["dropped"]}
        self.assertEqual(
            stages,
            {
                "ibn_kathir-2_255_tafsir-m21": "fidelity",
                "ibn_kathir-2_255_tafsir-m22": "schema",
            },
        )
        for entry in report["dropped"]:
            self.assertTrue(entry["reason"].strip())

    def test_annotations_object_input_gives_the_same_result(self):
        payload = {
            "annotations": ui_export_sample(),
            "exported_at": "2026-09-28T13:00:00Z",
        }
        code, summary = self.run_main(payload)
        self.assertEqual(code, 1)
        self.assertEqual(read_json(self.out), [read_json(EXAMPLE)])
        self.assertIn("المعتمد المكتوب: 1", summary)

    def test_single_record_object_input_is_accepted(self):
        code, summary = self.run_main(read_json(EXAMPLE))
        self.assertEqual(code, 0)
        self.assertEqual(read_json(self.out), [read_json(EXAMPLE)])
        self.assertIn("المعتمد المكتوب: 1", summary)

    # --- selection, ordering, duplicates ------------------------------------------

    def test_output_is_sorted_and_reproducible(self):
        payload = [
            record_for(17, 105, 0, 40, "ibn_kathir-17_105_tafsir-m01"),
            record_for(2, 255, 23720, 66, EXAMPLE_ID),
            record_for(2, 102, 0, 40, "ibn_kathir-2_102_tafsir-m03"),
        ]
        code, summary = self.run_main(payload)
        self.assertEqual(code, 0)
        self.assertIn("المعتمد المكتوب: 3", summary)
        written = read_json(self.out)
        self.assertEqual(
            [
                (r["quran"]["surah"], r["quran"]["ayah"], r["source"]["start_char"])
                for r in written
            ],
            [(2, 102, 0), (2, 255, 23720), (17, 105, 0)],
        )
        first_run = self.out.read_bytes()
        self.run_main(payload)
        self.assertEqual(first_run, self.out.read_bytes())

    def test_duplicate_annotation_id_keeps_the_latest_reviewed_at(self):
        older = record_for(2, 255, 23720, 66, EXAMPLE_ID, reviewed_at="2026-09-28T09:00:00Z")
        older["labels"] = {"source_method": ["M_SUNNAH"], "content_type": []}
        newer = record_for(2, 255, 23720, 66, EXAMPLE_ID, reviewed_at="2026-09-28T12:00:00Z")
        for payload in ([older, newer], [newer, older]):
            with self.subTest(first=payload[0]["review"]["reviewed_at"]):
                code, summary = self.run_main(payload)
                self.assertEqual(code, 1)
                self.assertIn("المكرر: 1", summary)
                written = read_json(self.out)
                self.assertEqual(len(written), 1)
                self.assertEqual(written[0]["labels"], newer["labels"])
                self.assertEqual(written[0]["review"]["reviewed_at"], "2026-09-28T12:00:00Z")

    def test_include_rejected_never_adds_working_states(self):
        approved = record_for(2, 255, 23720, 66, EXAMPLE_ID)
        rejected = record_for(2, 102, 0, 40, "ibn_kathir-2_102_tafsir-m01", status="rejected")
        ai = record_for(17, 105, 0, 40, "ibn_kathir-17_105_tafsir-m01", status="ai_proposed")
        under = record_for(17, 105, 40, 40, "ibn_kathir-17_105_tafsir-m02", status="under_review")
        payload = [approved, rejected, ai, under]

        code, summary = self.run_main(payload)
        self.assertEqual(code, 0)
        self.assertEqual(read_json(self.out), [approved])
        self.assertIn("المعتمد المكتوب: 1", summary)

        code, summary = self.run_main(payload, "--include-rejected")
        self.assertEqual(code, 0)
        self.assertEqual(
            [r["annotation_id"] for r in read_json(self.out)],
            ["ibn_kathir-2_102_tafsir-m01", EXAMPLE_ID],
        )
        self.assertIn("منها مرفوضة أُدرجت بـ --include-rejected: 1", summary)

        report = self.report(payload, "--include-rejected")
        self.assertEqual(
            (
                report["written"],
                report["written_approved"],
                report["written_rejected"],
                report["skipped"],
                report["dropped"],
            ),
            (2, 1, 1, 2, []),
        )
        report = self.report(payload)
        self.assertEqual(
            (
                report["written"],
                report["written_approved"],
                report["written_rejected"],
                report["skipped"],
            ),
            (1, 1, 0, 3),
        )

    # --- what gets dropped, and why ------------------------------------------------

    def test_fixture_record_with_unknown_field_fails_the_schema(self):
        payload = copy.deepcopy(ui_export_sample()[3])
        code, summary = self.run_main(payload)
        self.assertEqual(code, 1)
        self.assertEqual(read_json(self.out), [])
        self.assertIn(f"{SCHEMA_LINE}: 1", summary)
        report = self.report([payload])
        self.assertEqual((report["dropped_schema"], report["dropped_fidelity"]), (1, 0))
        self.assertEqual(report["dropped"][0]["stage"], "schema")
        self.assertIn("ui_note", report["dropped"][0]["reason"])

    def test_fixture_record_with_one_changed_letter_fails_fidelity(self):
        payload = copy.deepcopy(ui_export_sample()[2])
        code, summary = self.run_main(payload)
        self.assertEqual(code, 1)
        self.assertEqual(read_json(self.out), [])
        self.assertIn(f"{FIDELITY_LINE}: 1", summary)
        report = self.report([payload])
        self.assertEqual((report["dropped_schema"], report["dropped_fidelity"]), (0, 1))
        self.assertEqual(report["dropped"][0]["stage"], "fidelity")
        self.assertIn("text", report["dropped"][0]["reason"])

    def test_sha256_mismatch_fails_fidelity(self):
        payload = copy.deepcopy(read_json(EXAMPLE))
        payload["source"]["sha256"] = "0" * 64
        report = self.report([payload])
        self.assertEqual((report["written"], report["dropped_fidelity"]), (0, 1))
        self.assertIn("sha256", report["dropped"][0]["reason"])
        self.assertEqual(self.run_main([payload])[0], 1)
        self.assertEqual(read_json(self.out), [])

    def test_null_sha256_is_accepted_when_the_slice_matches(self):
        payload = copy.deepcopy(read_json(EXAMPLE))
        payload["source"]["sha256"] = None
        report = self.report([payload])
        self.assertEqual((report["written"], report["dropped"]), (1, []))

    def test_unknown_source_file_fails_fidelity(self):
        payload = copy.deepcopy(read_json(EXAMPLE))
        payload["source"]["source_id"] = "ibn_kathir_2_999"
        report = self.report([payload])
        self.assertEqual((report["written"], report["dropped_fidelity"]), (0, 1))
        self.assertIn("2_999", report["dropped"][0]["reason"])

    def test_sourceless_id_fails_fidelity(self):
        payload = copy.deepcopy(read_json(EXAMPLE))
        payload["source"]["source_id"] = "2_255"
        report = self.report([payload])
        self.assertEqual(report["dropped_fidelity"], 1)

    def test_inverted_offsets_fail_the_code_level_check(self):
        payload = copy.deepcopy(read_json(EXAMPLE))
        payload["source"]["start_char"] = 23786
        payload["source"]["end_char"] = 23720
        report = self.report([payload])
        # draft 2020-12 cannot express end_char > start_char, so the schema passes
        self.assertEqual((report["dropped_schema"], report["dropped_fidelity"]), (0, 1))
        self.assertIn("end_char", report["dropped"][0]["reason"])

    def test_dropped_records_are_never_written(self):
        sample = ui_export_sample()
        payload = [copy.deepcopy(sample[2]), copy.deepcopy(sample[3])]
        code, summary = self.run_main(payload)
        self.assertEqual(code, 1)
        self.assertEqual(read_json(self.out), [])
        self.assertIn("المعتمد المكتوب: 0", summary)

    # --- mapping, schema sanity, error exits, file bytes ---------------------------

    def test_source_file_mapping(self):
        self.assertEqual(exporter.source_file_for("ibn_kathir_2_255"), RAW_DIR / "2_255.txt")
        self.assertEqual(exporter.source_file_for("al_tabari_17_105"), RAW_DIR / "17_105.txt")
        self.assertIsNone(exporter.source_file_for("2_255"))
        self.assertIsNone(exporter.source_file_for(""))
        self.assertIsNone(exporter.source_file_for("ibn_kathir_2_255_extra"))

    def test_helper_records_and_the_example_pass_the_schema(self):
        validator = exporter.load_validator()
        for record in (
            read_json(EXAMPLE),
            ui_export_sample()[0],
            record_for(2, 255, 23720, 66, EXAMPLE_ID),
            record_for(2, 102, 0, 40, "ibn_kathir-2_102_tafsir-m01", status="rejected"),
            record_for(17, 105, 0, 40, "ibn_kathir-17_105_tafsir-m01", status="ai_proposed"),
        ):
            self.assertEqual(exporter.schema_errors(validator, record), [])

    def test_missing_input_file_exits_with_two(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = exporter.main([str(self.workspace / "nope.json"), "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("خطأ", buffer.getvalue())
        self.assertFalse(self.out.exists())

    def test_invalid_json_exits_with_two(self):
        path = self.workspace / "broken.json"
        path.write_bytes(b"{ not json")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = exporter.main([str(path), "--out", str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("خطأ", buffer.getvalue())

    def test_unknown_input_shape_exits_with_two(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = exporter.main(
                [str(self.write_input({"windows": []})), "--out", str(self.out)]
            )
        self.assertEqual(code, 2)
        self.assertIn("records", buffer.getvalue())

    def test_output_file_is_utf8_indented_json(self):
        code, _ = self.run_main([read_json(EXAMPLE)])
        self.assertEqual(code, 0)
        raw = self.out.read_bytes()
        self.assertIn(b'\n  {\n    "annotation_id"', raw)
        self.assertNotIn(b"\\u0627", raw)
        # UTF-8 Arabic from the schema example must appear literally (not \\uXXXX).
        example_slice = read_json(EXAMPLE)["text"][:8].encode("utf-8")
        self.assertTrue(example_slice)
        self.assertIn(example_slice, raw)
        self.assertEqual(read_json(self.out), [read_json(EXAMPLE)])

    # --- classic UI envelope {data_version, records} (synthetic only) -------------

    def _synth_record_and_pin(self) -> dict:
        pinned = self.workspace / "pinned"
        pinned.mkdir(parents=True, exist_ok=True)
        raw = SYNTHETIC_SOURCE.encode("utf-8")
        (pinned / "1_1.txt").write_bytes(raw)
        start, end = 0, 24
        return {
            "annotation_id": "synth_demo-1_1_window-m01",
            "quran": {"surah": 1, "ayah": 1},
            "tafsir": {"id": "synth_demo", "name": "مصدر اختباري ملفّق"},
            "source": {
                "source_id": "synth_demo_1_1",
                "sha256": hashlib.sha256(raw).hexdigest(),
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

    def test_records_envelope_matching_version_is_written(self):
        record = self._synth_record_and_pin()
        pinned = self.workspace / "pinned"
        payload = {"data_version": SYNTH_VERSION, "records": [record]}
        with mock.patch.dict(
            exporter.TAFSIR_SOURCE_DIRS,
            {"synth_demo": pinned, "default": pinned},
            clear=False,
        ), mock.patch.object(
            exporter, "current_data_version", return_value=SYNTH_VERSION
        ):
            code, summary = self.run_main(payload)
        self.assertEqual(code, 0)
        self.assertTrue(self.out.is_file())
        self.assertEqual(read_json(self.out), [record])
        self.assertIn("المعتمد المكتوب: 1", summary)

    def test_records_envelope_version_mismatch_refuses_write(self):
        record = self._synth_record_and_pin()
        payload = {"data_version": "wrongversion1", "records": [record]}
        preexisting = b'[{"keep":true}]'
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.out.write_bytes(preexisting)
        with mock.patch.object(
            exporter, "current_data_version", return_value=SYNTH_VERSION
        ):
            code, summary = self.run_main(payload)
        self.assertEqual(code, 2)
        self.assertEqual(summary.strip(), exporter.VERSION_MISMATCH_MSG)
        self.assertEqual(self.out.read_bytes(), preexisting)

    def test_records_envelope_empty_writes_nothing_exit_zero(self):
        payload = {"data_version": SYNTH_VERSION, "records": []}
        with mock.patch.object(
            exporter, "current_data_version", return_value=SYNTH_VERSION
        ):
            code, summary = self.run_main(payload)
        self.assertEqual(code, 0, msg="empty records → exit 0 (no drops)")
        self.assertEqual(read_json(self.out), [])
        self.assertIn("المعتمد المكتوب: 0", summary)
        self.assertIn("عدد المدخل: 0", summary)


if __name__ == "__main__":
    unittest.main()
