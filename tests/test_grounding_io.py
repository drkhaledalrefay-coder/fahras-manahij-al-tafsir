"""Tests for Phase 0 grounding contract (LANE B: classifier + runner input side).

Covers:
- Request contains packet_sha256 canonical hash; no outside context injected.
- Written payload carries code-computed packet_sha256 and input_assurance='api_packet',
  overwriting any forged model values.
- Manual runner input (--manual-in) saves input_assurance='manual_unverified' and
  no valid hash (packet_sha256 is None/invalid).
- Failure paths (network error, timeout, invalid JSON / invalid spans after retry)
  produce a failure record (RUN_FAILURE / MODEL_OUTPUT_INVALID) and write NO moves file.
- sanitize_moves_payload drops any unknown keys at root, move, and reference levels.
- Optional rationale_ar labeled as ungrounded note and references required to have evidence spans.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import classify_api  # noqa: E402
import grounding_contract  # noqa: E402
import run_window  # noqa: E402

PACKET_FIXTURE = ROOT / "data" / "multi" / "al_tabari" / "packets" / "2_102.json"
SECRET_KEY = "sk-test-secret-never-expose"


def _fake_chat_body(content_obj: dict | str) -> bytes:
    if isinstance(content_obj, dict):
        text = json.dumps(content_obj, ensure_ascii=False)
    else:
        text = str(content_obj)
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode("utf-8")


def _valid_moves_payload(window: str = "2_102") -> dict:
    return {
        "window": window,
        "moves": [
            {
                "move_id": "m01",
                "span_ids": ["s288", "s289"],
                "primary": "M_LUGHA",
                "secondary": [],
                "content_tags": ["C_TAFSIR"],
                "certainty": "strong",
                "evidence_span_ids": ["s288"],
                "author_verdict_span_ids": [],
                "references": {"verses": [], "hadith": [], "persons": []},
                "alternatives": [],
                "rationale_ar": "بيان لغوي",
            }
        ],
    }


class TestGroundingIO(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(PACKET_FIXTURE.is_file(), f"missing fixture {PACKET_FIXTURE}")
        self.packet = classify_api.load_packet(PACKET_FIXTURE)
        self.expected_hash = grounding_contract.packet_sha256(self.packet)

    def test_request_contains_packet_sha256_and_no_injected_content(self) -> None:
        calls: list[dict] = []

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            calls.append({"url": url, "headers": headers, "body": body})
            return _fake_chat_body(_valid_moves_payload())

        with tempfile.TemporaryDirectory() as tmp:
            classify_api.classify(
                PACKET_FIXTURE,
                model="test-model",
                base_url="https://example.test/v1",
                out_dir=tmp,
                api_key=SECRET_KEY,
                http_post=http_post,
            )

        self.assertEqual(len(calls), 1)
        req_data = json.loads(calls[0]["body"].decode("utf-8"))
        messages = req_data["messages"]
        self.assertEqual(len(messages), 2)

        # Assert system message is fixed instruction
        self.assertEqual(
            messages[0]["content"],
            "You are a tafsir methodology classifier. "
            "Reply with a single JSON object only. "
            "Use span ids from the packet; never invent ids; never quote long source text.",
        )

        user_content = messages[1]["content"]
        # Assert packet_sha256 header matches canonical hash
        self.assertIn(f"packet_sha256: {self.expected_hash}", user_content)
        self.assertIn(f"window_id: {self.packet.get('window_id')}", user_content)
        self.assertIn(f"ayah: {self.packet.get('ayah')}", user_content)

        # Assert no stray repo paths or outside context strings are injected
        self.assertNotIn("quran.db", user_content)
        self.assertNotIn("tests/test_", user_content)
        self.assertNotIn(SECRET_KEY, user_content)

    def test_written_payload_hash_and_input_assurance_overwrites_forgery(self) -> None:
        forged_reply = _valid_moves_payload()
        forged_reply[grounding_contract.PACKET_SHA_FIELD] = "deadbeef" * 8
        forged_reply[grounding_contract.INPUT_ASSURANCE_FIELD] = "fake_assurance"
        forged_reply["extra_model_key"] = "should_be_dropped"

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            return _fake_chat_body(forged_reply)

        with tempfile.TemporaryDirectory() as tmp:
            result = classify_api.classify(
                PACKET_FIXTURE,
                model="deepseek-chat",
                base_url="https://example.test/v1",
                out_dir=tmp,
                api_key=SECRET_KEY,
                http_post=http_post,
            )
            saved_path = result["path"]
            self.assertIsNotNone(saved_path)
            assert saved_path is not None
            self.assertTrue(saved_path.is_file())

            saved = json.loads(saved_path.read_bytes().decode("utf-8"))
            # Must equal the canonically computed hash, never the forged model reply value
            self.assertEqual(saved[grounding_contract.PACKET_SHA_FIELD], self.expected_hash)
            self.assertNotEqual(saved[grounding_contract.PACKET_SHA_FIELD], "deadbeef" * 8)
            self.assertEqual(
                saved[grounding_contract.INPUT_ASSURANCE_FIELD],
                grounding_contract.INPUT_API_PACKET,
            )
            self.assertNotIn("extra_model_key", saved)

            # In-memory returned payload must also carry identical values
            self.assertEqual(
                result["payload"][grounding_contract.PACKET_SHA_FIELD],
                self.expected_hash,
            )
            self.assertEqual(
                result["payload"][grounding_contract.INPUT_ASSURANCE_FIELD],
                grounding_contract.INPUT_API_PACKET,
            )

    def test_manual_in_saves_unverified_assurance_and_no_valid_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_base = Path(tmp) / "base"
            pkts_dir = tmp_base / "packets"
            pkts_dir.mkdir(parents=True)
            # Copy fixture packet to isolated tmp base
            shutil.copy(PACKET_FIXTURE, pkts_dir / "2_102.json")

            manual_reply_file = Path(tmp) / "reply.json"
            forged_reply = _valid_moves_payload()
            forged_reply["packet_sha256"] = "deadbeef" * 8
            manual_reply_file.write_bytes(
                json.dumps(forged_reply, ensure_ascii=False).encode("utf-8")
            )

            buf = io.StringIO()
            with mock.patch("run_window.run_verifier") as mock_ver:
                mock_ver.return_value = {"summary": {"move_count": 1}}
                with redirect_stdout(buf):
                    ret = run_window.main(
                        [
                            "--base",
                            str(tmp_base),
                            "--window",
                            "2_102",
                            "--manual-in",
                            str(manual_reply_file),
                        ]
                    )

            self.assertEqual(ret, 0)
            out_msg = buf.getvalue()
            # Clear Arabic + English line required by B2
            self.assertIn("manual reply = unverified input, never nominated", out_msg)
            self.assertIn("مدخل يدوي غير مضمون", out_msg)

            # Locate written moves file
            moves_files = list((tmp_base / "moves").glob("manual_*/*.json"))
            self.assertEqual(len(moves_files), 1)
            saved = json.loads(moves_files[0].read_bytes().decode("utf-8"))

            self.assertEqual(
                saved.get(grounding_contract.INPUT_ASSURANCE_FIELD),
                grounding_contract.INPUT_MANUAL_UNVERIFIED,
            )
            # Must NOT get a packet hash that would let it pass
            sha_val = saved.get(grounding_contract.PACKET_SHA_FIELD)
            self.assertTrue(sha_val is None or sha_val != self.expected_hash)
            self.assertNotEqual(sha_val, "deadbeef" * 8)

    def test_manual_out_states_replies_are_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_base = Path(tmp) / "base"
            (tmp_base / "packets").mkdir(parents=True)
            shutil.copy(PACKET_FIXTURE, tmp_base / "packets" / "2_102.json")
            prompt_file = Path(tmp) / "prompt.txt"

            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = run_window.main(
                    [
                        "--base",
                        str(tmp_base),
                        "--window",
                        "2_102",
                        "--manual-out",
                        str(prompt_file),
                    ]
                )

            self.assertEqual(ret, 0)
            text = prompt_file.read_bytes().decode("utf-8")
            self.assertIn("unverified input", text)
            self.assertIn("specialist review only", text)
            self.assertIn("مدخل غير مضمون", text)

    def test_network_failure_returns_run_failure_record_and_writes_no_moves(self) -> None:
        def http_post_fail(url: str, headers: dict, body: bytes) -> bytes:
            raise urllib.error.URLError("Connection refused")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(classify_api.ClassifyError) as ctx:
                classify_api.classify(
                    PACKET_FIXTURE,
                    model="fail-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET_KEY,
                    http_post=http_post_fail,
                )

            exc = ctx.exception
            rec = exc.record
            self.assertEqual(rec["window_id"], "2_102")
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["reason_code"], "RUN_FAILURE")
            self.assertIn("Connection refused", rec["error"])

            # Exception index access also works
            self.assertEqual(exc["reason_code"], "RUN_FAILURE")
            self.assertEqual(exc["status"], "failed")

            # Assert NO moves file was written
            ann_dir = Path(tmp) / "fail_model"
            self.assertFalse(ann_dir.exists() and any(ann_dir.glob("*.json")))

    def test_garbage_twice_returns_model_output_invalid_record_and_writes_no_moves(self) -> None:
        call_count = {"n": 0}

        def http_post_garbage(url: str, headers: dict, body: bytes) -> bytes:
            call_count["n"] += 1
            return _fake_chat_body("<html>502 Bad Gateway</html>")

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(classify_api.ClassifyError) as ctx:
                classify_api.classify(
                    PACKET_FIXTURE,
                    model="garbage-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET_KEY,
                    http_post=http_post_garbage,
                )

            # Validated that retry occurred (called twice)
            self.assertEqual(call_count["n"], 2)

            exc = ctx.exception
            rec = exc.record
            self.assertEqual(rec["window_id"], "2_102")
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["reason_code"], "MODEL_OUTPUT_INVALID")
            self.assertIn("invalid JSON", rec["error"])

            ann_dir = Path(tmp) / "garbage_model"
            self.assertFalse(ann_dir.exists() and any(ann_dir.glob("*.json")))

    def test_invalid_spans_twice_returns_model_output_invalid_record(self) -> None:
        bad = _valid_moves_payload()
        bad["moves"][0]["span_ids"] = ["s_DOES_NOT_EXIST"]
        call_count = {"n": 0}

        def http_post_bad_spans(url: str, headers: dict, body: bytes) -> bytes:
            call_count["n"] += 1
            return _fake_chat_body(bad)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(classify_api.ClassifyError) as ctx:
                classify_api.classify(
                    PACKET_FIXTURE,
                    model="bad-spans-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET_KEY,
                    http_post=http_post_bad_spans,
                )

            self.assertEqual(call_count["n"], 2)
            rec = ctx.exception.record
            self.assertEqual(rec["window_id"], "2_102")
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["reason_code"], "MODEL_OUTPUT_INVALID")
            self.assertIn("invalid span ids", rec["error"].lower())

            ann_dir = Path(tmp) / "bad_spans_model"
            self.assertFalse(ann_dir.exists() and any(ann_dir.glob("*.json")))

    def test_run_window_cli_failure_prints_record_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_base = Path(tmp) / "base"
            (tmp_base / "packets").mkdir(parents=True)
            shutil.copy(PACKET_FIXTURE, tmp_base / "packets" / "2_102.json")

            def http_fail(url: str, headers: dict, body: bytes) -> bytes:
                raise urllib.error.URLError("DNS lookup failed")

            buf = io.StringIO()
            with mock.patch.dict(os.environ, {"LLM_API_KEY": SECRET_KEY}):
                with mock.patch("classify_api._default_http_post", side_effect=http_fail):
                    with redirect_stdout(buf):
                        ret = run_window.main(
                            [
                                "--base",
                                str(tmp_base),
                                "--window",
                                "2_102",
                                "--api",
                                "--model",
                                "cli-fail",
                                "--base-url",
                                "https://example.test/v1",
                            ]
                        )

            self.assertNotEqual(ret, 0)
            printed = buf.getvalue().strip()
            # Must print failure record as JSON
            rec = json.loads(printed)
            self.assertEqual(rec["window_id"], "2_102")
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["reason_code"], "RUN_FAILURE")
            self.assertIn("DNS lookup failed", rec["error"])

    def test_sanitize_moves_payload_drops_unknown_keys(self) -> None:
        dirty_payload = {
            "window": "2_102",
            "unknown_root_key": "drop_root",
            "packet_sha256": "forged_sha",
            "input_assurance": "forged_assurance",
            "moves": [
                {
                    "move_id": "m01",
                    "span_ids": ["s288"],
                    "primary": "M_LUGHA",
                    "secondary": [],
                    "content_tags": ["C_TAFSIR"],
                    "certainty": "strong",
                    "evidence_span_ids": ["s288"],
                    "author_verdict_span_ids": [],
                    "references": {
                        "verses": ["2:102"],
                        "hadith": [],
                        "persons": ["مجاهد"],
                        "extra_ref_key": "drop_ref",
                    },
                    "alternatives": [],
                    "unknown_move_key": "drop_move",
                    "source_text": "do not copy source text",
                    "rationale_ar": "ملاحظة موجزة",
                }
            ],
        }

        cleaned = classify_api.sanitize_moves_payload(dirty_payload, "2_102")

        # Top-level keys must ONLY be "window" and "moves"
        self.assertEqual(set(cleaned.keys()), {"window", "moves"})
        self.assertNotIn("unknown_root_key", cleaned)
        self.assertNotIn("packet_sha256", cleaned)
        self.assertNotIn("input_assurance", cleaned)

        # Move level keys
        move = cleaned["moves"][0]
        self.assertNotIn("unknown_move_key", move)
        self.assertNotIn("source_text", move)
        self.assertEqual(move["rationale_ar"], "ملاحظة موجزة")

        # References level keys
        refs = move["references"]
        self.assertEqual(set(refs.keys()), {"verses", "hadith", "persons"})
        self.assertNotIn("extra_ref_key", refs)

        # When rationale_ar is omitted, it remains omitted (optional)
        dirty_without_rationale = {
            "window": "2_102",
            "moves": [
                {
                    "move_id": "m02",
                    "span_ids": ["s288"],
                    "primary": "M_RAY",
                }
            ],
        }
        cleaned_no_rat = classify_api.sanitize_moves_payload(
            dirty_without_rationale, "2_102"
        )
        self.assertNotIn("rationale_ar", cleaned_no_rat["moves"][0])

    def test_output_schema_and_prompt_labels_rationale_ar_and_references(self) -> None:
        user_prompt = classify_api.build_user_prompt(self.packet)

        # Label in the schema text
        self.assertIn('"rationale_ar": "ملاحظة غير مُسنَدة — لا تُعرض دليلاً"', user_prompt)

        # Exact new instruction sentence for rationale_ar
        expected_rationale_note = "حقل rationale_ar اختياري: ملاحظة غير مُسنَدة — لا تُعرض دليلاً."
        self.assertIn(expected_rationale_note, user_prompt)

        # Exact new instruction sentence requiring references to be backed by evidence_span_ids
        expected_ref_instruction = (
            "كل مرجع في references (آيات verses أو أحاديث hadith أو أعلام persons) "
            "يجب أن يسنده معرّف شاهد في evidence_span_ids."
        )
        self.assertIn(expected_ref_instruction, user_prompt)

        # Ensure packet fixture itself was not mutated
        orig_rat = self.packet["output_schema"]["moves"][0]["rationale_ar"]
        self.assertEqual(orig_rat, "≤25 words, no quotes >4 words")

    def test_fenced_bad_json_twice_returns_model_output_invalid_and_run_window_exits_nonzero(
        self,
    ) -> None:
        call_count = {"n": 0}
        fenced_bad_json = "```json\n{bad: json here}\n```"

        def http_post_fenced_bad(url: str, headers: dict, body: bytes) -> bytes:
            call_count["n"] += 1
            return _fake_chat_body(fenced_bad_json)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(classify_api.ClassifyError) as ctx:
                classify_api.classify(
                    PACKET_FIXTURE,
                    model="fenced-bad-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET_KEY,
                    http_post=http_post_fenced_bad,
                )

            # Assert retry happened
            self.assertEqual(call_count["n"], 2)

            exc = ctx.exception
            rec = exc.record
            self.assertEqual(rec["window_id"], "2_102")
            self.assertEqual(rec["status"], "failed")
            self.assertEqual(rec["reason_code"], "MODEL_OUTPUT_INVALID")
            self.assertIn("invalid JSON", rec["error"])

            # Assert NO moves file written
            ann_dir = Path(tmp) / "fenced_bad_model"
            self.assertFalse(ann_dir.exists() and any(ann_dir.glob("*.json")))

        # Now test run_window CLI execution with fenced bad JSON twice
        with tempfile.TemporaryDirectory() as tmp:
            tmp_base = Path(tmp) / "base"
            (tmp_base / "packets").mkdir(parents=True)
            shutil.copy(PACKET_FIXTURE, tmp_base / "packets" / "2_102.json")

            buf = io.StringIO()
            with mock.patch.dict(os.environ, {"LLM_API_KEY": SECRET_KEY}):
                with mock.patch("classify_api._default_http_post", side_effect=http_post_fenced_bad):
                    with redirect_stdout(buf):
                        ret = run_window.main(
                            [
                                "--base",
                                str(tmp_base),
                                "--window",
                                "2_102",
                                "--api",
                                "--model",
                                "fenced-cli-fail",
                                "--base-url",
                                "https://example.test/v1",
                            ]
                        )

            # Assert run_window exits non-zero
            self.assertNotEqual(ret, 0)
            printed = buf.getvalue().strip()
            cli_rec = json.loads(printed)
            self.assertEqual(cli_rec["window_id"], "2_102")
            self.assertEqual(cli_rec["status"], "failed")
            self.assertEqual(cli_rec["reason_code"], "MODEL_OUTPUT_INVALID")

            # Assert NO moves file written under tmp_base
            moves_dir = tmp_base / "moves"
            self.assertFalse(moves_dir.exists() and any(moves_dir.rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
