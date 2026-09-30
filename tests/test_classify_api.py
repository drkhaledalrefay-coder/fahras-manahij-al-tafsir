"""Offline tests for classify_api / run_window (fake HTTP, no real network)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import classify_api  # noqa: E402
import run_window  # noqa: E402

PACKET = ROOT / "data" / "multi" / "al_tabari" / "packets" / "2_102.json"
SECRET = "sk-test-secret-KEY-never-log-me"


def _fake_openai_body(content_obj: dict) -> bytes:
    return json.dumps(
        {
            "choices": [
                {"message": {"content": json.dumps(content_obj, ensure_ascii=False)}}
            ]
        }
    ).encode("utf-8")


def _valid_payload(window: str = "2_102") -> dict:
    # Use real span ids from the al_tabari 2_102 packet
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
                "rationale_ar": "اختبار",
            }
        ],
    }


class TestClassifyApi(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(PACKET.is_file(), f"missing fixture packet {PACKET}")

    def test_valid_reply_saved(self) -> None:
        calls: list[dict] = []

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            calls.append({"url": url, "headers": headers, "body": body})
            return _fake_openai_body(_valid_payload())

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = classify_api.classify(
                PACKET,
                model="deepseek-chat",
                base_url="https://example.test/v1",
                out_dir=out,
                api_key=SECRET,
                http_post=http_post,
            )
            self.assertEqual(len(calls), 1)
            path = result["path"]
            self.assertIsNotNone(path)
            assert path is not None
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent.name, "deepseek_chat")
            saved = json.loads(path.read_bytes().decode("utf-8"))
            self.assertEqual(saved["window"], "2_102")
            self.assertEqual(saved["moves"][0]["span_ids"], ["s288", "s289"])
            self.assertNotIn("text", saved["moves"][0])
            self.assertNotIn("source", saved["moves"][0])

    def test_invalid_span_id_rejected(self) -> None:
        bad = _valid_payload()
        bad["moves"][0]["span_ids"] = ["s288", "s_DOES_NOT_EXIST"]
        still_bad = _valid_payload()
        still_bad["moves"][0]["evidence_span_ids"] = ["nope"]
        replies = [_fake_openai_body(bad), _fake_openai_body(still_bad)]

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            return replies.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(classify_api.ClassifyError) as ctx:
                classify_api.classify(
                    PACKET,
                    model="test-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET,
                    http_post=http_post,
                )
            self.assertIn("invalid span ids", str(ctx.exception).lower())
            # No file written under annotator dir
            ann = Path(tmp) / "test_model"
            self.assertFalse(ann.exists() and any(ann.glob("*.json")))

    def test_invalid_then_valid_on_retry(self) -> None:
        bad = _valid_payload()
        bad["moves"][0]["span_ids"] = ["s_FAKE"]
        good = _valid_payload()
        bodies = [_fake_openai_body(bad), _fake_openai_body(good)]
        seen_bodies: list[str] = []

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            seen_bodies.append(body.decode("utf-8"))
            return bodies.pop(0)

        with tempfile.TemporaryDirectory() as tmp:
            result = classify_api.classify(
                PACKET,
                model="retry-model",
                base_url="https://example.test/v1",
                out_dir=tmp,
                api_key=SECRET,
                http_post=http_post,
            )
            self.assertEqual(len(seen_bodies), 2)
            self.assertIn("s_FAKE", seen_bodies[1])  # error fed back
            self.assertTrue(result["path"].is_file())

    def test_api_key_never_logged(self) -> None:
        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            return _fake_openai_body(_valid_payload())

        buf = io.StringIO()
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(buf), redirect_stderr(err):
                classify_api.classify(
                    PACKET,
                    model="log-check",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    api_key=SECRET,
                    http_post=http_post,
                )
                # Also exercise run_window path printing
                print("ok")
        combined = buf.getvalue() + err.getvalue()
        self.assertNotIn(SECRET, combined)
        self.assertNotIn("sk-test-secret", combined)

    def test_dry_run_no_network(self) -> None:
        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            raise AssertionError("network should not be called in dry-run")

        with tempfile.TemporaryDirectory() as tmp:
            result = classify_api.classify(
                PACKET,
                model="dry-model",
                base_url="https://example.test/v1",
                out_dir=tmp,
                api_key=SECRET,
                http_post=http_post,
                dry_run=True,
            )
            self.assertTrue(result["dry_run"])
            self.assertIsNone(result["path"])
            self.assertEqual(len(result["messages"]), 2)

    def test_run_window_dry_run_cli(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_window.main(
                ["--tafsir", "al_tabari", "--window", "2_102", "--dry-run"]
            )
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("dry-run", out.lower())
        self.assertIn("2_102", out)
        self.assertNotIn(SECRET, out)

    def test_run_window_manual_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "prompt.txt"
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = run_window.main(
                    [
                        "--tafsir",
                        "al_tabari",
                        "--window",
                        "2_102",
                        "--manual-out",
                        str(prompt_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(prompt_path.is_file())
            text = prompt_path.read_bytes().decode("utf-8")
            self.assertIn("s288", text)
            self.assertIn("مخطط الإخراج", text)
            self.assertIn("window", text)


class TestKeyEnv(unittest.TestCase):
    def test_key_only_from_env_when_not_passed(self) -> None:
        called = {"n": 0}

        def http_post(url: str, headers: dict, body: bytes) -> bytes:
            called["n"] += 1
            auth = headers.get("Authorization", "")
            self.assertTrue(auth.startswith("Bearer "))
            self.assertIn(SECRET, auth)
            return _fake_openai_body(_valid_payload())

        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "LLM_API_KEY": SECRET}
            with mock.patch.dict(os.environ, env, clear=False):
                classify_api.classify(
                    PACKET,
                    model="env-model",
                    base_url="https://example.test/v1",
                    out_dir=tmp,
                    http_post=http_post,
                )
        self.assertEqual(called["n"], 1)


if __name__ == "__main__":
    unittest.main()
