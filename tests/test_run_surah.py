"""Tests for run_surah pipeline reproducibility and run_window --base flag."""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import run_surah  # noqa: E402
import run_window  # noqa: E402


def resolve_quran_db() -> Path | None:
    env_path = os.environ.get("QURAN_DB")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


class TestRunSurah(unittest.TestCase):
    def test_run_window_base_dry_run_prints_no_network_call(self) -> None:
        """run_window --base --dry-run on an anfal window prints 'dry-run: no network call'."""
        anfal_base = ROOT / "data" / "anfal" / "al_tabari"
        self.assertTrue(
            (anfal_base / "packets" / "8_2.json").is_file(),
            f"committed packet missing: {anfal_base / 'packets' / '8_2.json'}",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_window.main(
                ["--base", str(anfal_base), "--window", "8_2", "--dry-run"]
            )
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("dry-run: no network call", out)
        self.assertIn("window: 8_2", out)

    def test_regenerate_al_tabari_windows_byte_identical(self) -> None:
        """Regenerating 3 windows of al_tabari surah 8 into temp dir yields byte-identical files."""
        db_path = resolve_quran_db()
        if not db_path:
            self.skipTest("set QURAN_DB to the path of quran.db (see docs/RUN.md)")

        test_ayat = [2, 3, 4]
        committed_base = ROOT / "data" / "anfal" / "al_tabari"
        self.assertTrue(committed_base.is_dir(), f"missing committed dir {committed_base}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_base = Path(tmp)
            generated_ids = run_surah.run_surah(
                db_path=db_path,
                tafsir="al_tabari",
                surah=8,
                ayat=test_ayat,
                base=tmp_base,
            )
            self.assertEqual(generated_ids, ["8_2", "8_3", "8_4"])

            # Verify byte-identical across all 6 directory layers
            subdirs = ["raw", "layers", "spans", "windows", "markers", "packets"]
            for sub in subdirs:
                for ayah in test_ayat:
                    ext = ".txt" if sub == "raw" else ".json"
                    fname = f"8_{ayah}{ext}"
                    gen_file = tmp_base / sub / fname
                    com_file = committed_base / sub / fname
                    self.assertTrue(gen_file.is_file(), f"Missing generated file: {gen_file}")
                    self.assertTrue(com_file.is_file(), f"Missing committed file: {com_file}")
                    self.assertEqual(
                        gen_file.read_bytes(),
                        com_file.read_bytes(),
                        f"Byte mismatch in {sub}/{fname}",
                    )

            # Idempotence check: second run should skip and preserve identical files
            buf = io.StringIO()
            with redirect_stdout(buf):
                rerun_ids = run_surah.run_surah(
                    db_path=db_path,
                    tafsir="al_tabari",
                    surah=8,
                    ayat=test_ayat,
                    base=tmp_base,
                )
            self.assertEqual(rerun_ids, ["8_2", "8_3", "8_4"])
            skip_output = buf.getvalue()
            for ayah in test_ayat:
                self.assertIn(f"skip 8_{ayah}", skip_output)

    def test_run_surah_dry_run_never_calls_model(self) -> None:
        """--dry-run never calls a model and passes --dry-run to classifier."""
        db_path = resolve_quran_db()
        if not db_path:
            self.skipTest("set QURAN_DB to the path of quran.db (see docs/RUN.md)")

        committed_base = ROOT / "data" / "anfal" / "al_tabari"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = run_surah.main(
                [
                    "--db",
                    str(db_path),
                    "--tafsir",
                    "al_tabari",
                    "--surah",
                    "8",
                    "--ayat",
                    "2",
                    "--base",
                    str(committed_base),
                    "--dry-run",
                ]
            )
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("dry-run", out)
        self.assertIn("no network call", out)

    def test_classify_stops_on_http_429(self) -> None:
        """--classify loops run_window.py and stops on the first HTTP 429 with clear message."""
        fake_windows = ["8_2", "8_3", "8_4"]

        def fake_run(cmd, capture_output=True, text=True, timeout=120):
            mock_res = mock.MagicMock()
            if "8_2" in cmd:
                mock_res.returncode = 1
                mock_res.stdout = ""
                mock_res.stderr = "ClassifyError: HTTP 429: Too Many Requests - rate limit exceeded"
                return mock_res
            # Should never reach 8_3 or 8_4
            raise AssertionError("Classification did not stop on HTTP 429!")

        buf = io.StringIO()
        with mock.patch("subprocess.run", side_effect=fake_run):
            with redirect_stdout(buf):
                run_surah.run_classification_loop(
                    Path("data/anfal/al_tabari"),
                    fake_windows,
                    dry_run=False,
                    time_cap=30,
                )
        output = buf.getvalue()
        self.assertIn("HTTP 429 rate limit exceeded on window 8_2", output)
        self.assertIn("Stopping classification chain on first HTTP 429.", output)


if __name__ == "__main__":
    unittest.main()
