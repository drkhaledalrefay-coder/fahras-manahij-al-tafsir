"""Offline tests for demo_server (no real network / no real LLM)."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import demo_server  # noqa: E402

SECRET = "sk-test-secret-KEY-never-echo-me"
TAFSIR = "al_tabari"
WINDOW = "2_102"
REL_BASE = Path("data") / "multi" / "al_tabari"


def _copy_minimal_tree(dest_root: Path) -> None:
    """Temp project root with web/ + one tafsir tree (packets/windows/markers/moves)."""
    src_base = ROOT / REL_BASE
    dst_base = dest_root / REL_BASE
    for sub in ("packets", "windows", "markers"):
        (dst_base / sub).mkdir(parents=True, exist_ok=True)
        src = src_base / sub / f"{WINDOW}.json"
        shutil.copy2(src, dst_base / sub / f"{WINDOW}.json")
    donor_dir = dst_base / "moves" / "deepseek"
    donor_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        src_base / "moves" / "deepseek" / f"{WINDOW}.json",
        donor_dir / f"{WINDOW}.json",
    )
    web_src = ROOT / "web"
    web_dst = dest_root / "web"
    web_dst.mkdir(parents=True, exist_ok=True)
    (web_dst / "fahras.html").write_text("<!doctype html><title>t</title></body>", encoding="utf-8")
    if (web_src / "fahras.html").is_file():
        shutil.copy2(web_src / "fahras.html", web_dst / "fahras.html")


def _json_req(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    hdrs = {"Host": "127.0.0.1:8791"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = Request(url, data=data, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return e.code, payload, raw


def _raw_request(
    host: str,
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict | None = None,
) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection(host, port, timeout=30)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    if headers:
        hdrs.update(headers)
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def _tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    if not path.exists():
        return h.hexdigest()
    for fp in sorted(path.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(path).as_posix().encode("utf-8")
        h.update(rel)
        h.update(b"\0")
        h.update(fp.read_bytes())
    return h.hexdigest()


def _fake_dirs() -> set[Path]:
    return set(Path(tempfile.gettempdir()).glob("tafsir-demo-fake-*"))


class DemoServerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _copy_minimal_tree(self.root)
        self.httpd = demo_server.serve(
            port=0, root=self.root, fake=False, rebuild=False
        )
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._tmp.cleanup()

    def test_health_without_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            os.environ.pop("LLM_API_KEY", None)
            status, data, _ = _json_req(f"{self.base}/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertFalse(data["key_present"])
        self.assertFalse(data["fake"])
        self.assertNotIn("LLM_API_KEY", json.dumps(data))

    def test_bad_tafsir_window_400(self) -> None:
        status, data, _ = _json_req(
            f"{self.base}/api/run",
            method="POST",
            body={"tafsir": "AL-TABARI", "window": "2_102"},
        )
        self.assertEqual(status, 400)
        status2, _, _ = _json_req(
            f"{self.base}/api/run",
            method="POST",
            body={"tafsir": "al_tabari", "window": "2-102"},
        )
        self.assertEqual(status2, 400)
        status3, _, _ = _json_req(
            f"{self.base}/api/run",
            method="POST",
            body={"tafsir": "al_tabari", "window": "9_999"},
        )
        self.assertEqual(status3, 400)

    def test_non_local_origin_403(self) -> None:
        status, data, _ = _json_req(
            f"{self.base}/api/run",
            method="POST",
            body={"tafsir": TAFSIR, "window": WINDOW},
            headers={"Origin": "http://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertIn("forbidden", (data.get("error") or "").lower())

    def test_hostile_host_403(self) -> None:
        for host in ("evil.com", "127.0.0.1.evil.com", "evil.com:8791"):
            status, data = _raw_request(
                "127.0.0.1",
                self.port,
                "GET",
                "/api/health",
                headers={"Host": host},
            )
            self.assertEqual(status, 403, host)
            self.assertNotIn(SECRET.encode(), data)

    def test_path_traversal_404(self) -> None:
        marker = b"class DemoState"
        # Ensure the target file exists so a successful read would contain it
        demo_py = ROOT / "src" / "demo_server.py"
        self.assertTrue(demo_py.is_file())
        self.assertIn(marker, demo_py.read_bytes())
        paths = [
            "/../x",
            "/%2e%2e/x",
            "/..%2fsrc/demo_server.py",
            "/private/../../fahras.html",
            "/../src/demo_server.py",
            "/%2e%2e%2fsrc%2fdemo_server.py",
        ]
        for path in paths:
            status, body = _raw_request("127.0.0.1", self.port, "GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(marker, body)
            self.assertNotIn(b"DemoState", body)

    def test_ads_and_drive_path_404(self) -> None:
        """Reject Windows ADS / alternate streams / drive-letter / backslash escapes."""
        paths = [
            "/fahras.html::$DATA",
            "/fahras.html:stream",
            "/fahras.html%3A%3A%24DATA",
            "/fahras.html%3Astream",
            "/C:/Windows/win.ini",
            "/C%3A/Windows/win.ini",
            "/c:/foo",
            "/..\\src\\demo_server.py",
            "/%5c%2e%2e%5csrc%5cdemo_server.py",
            "/web\\..\\src\\demo_server.py",
        ]
        for path in paths:
            status, body = _raw_request("127.0.0.1", self.port, "GET", path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"class DemoState", body)
            self.assertNotIn(b"ai-run-btn", body)

    def test_fahras_response_injects_demo_not_on_disk(self) -> None:
        status, body = _raw_request("127.0.0.1", self.port, "GET", "/fahras.html")
        self.assertEqual(status, 200)
        self.assertIn(b"ai-run-btn", body)
        self.assertIn(b"/api/health", body)
        self.assertIn(b"/api/run", body)
        disk = (self.root / "web" / "fahras.html").read_bytes()
        self.assertNotIn(b"ai-run-btn", disk)
        self.assertNotIn(b"/api/health", disk)
        self.assertNotIn(b"/api/run", disk)

    def test_content_length_bounds(self) -> None:
        run_path = "/api/run"
        # missing
        status, body = _raw_request(
            "127.0.0.1",
            self.port,
            "POST",
            run_path,
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        # http.client may auto-set Content-Length; force omit via custom
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)

        class NoCL(http.client.HTTPConnection):
            def _send_output(self, message_body=None, encode_chunked=False):  # noqa: N802
                self._buffer = [b for b in self._buffer if not b.lower().startswith(b"content-length")]
                return http.client.HTTPConnection._send_output(self, message_body, encode_chunked)

        conn = NoCL("127.0.0.1", self.port, timeout=30)
        conn.putrequest("POST", run_path)
        conn.putheader("Host", f"127.0.0.1:{self.port}")
        conn.putheader("Content-Type", "application/json")
        conn.endheaders(b"{}")
        resp = conn.getresponse()
        raw = resp.read()
        self.assertEqual(resp.status, 400)
        self.assertIn(b"Content-Length", raw)
        conn.close()

        # negative
        status, raw = _raw_request(
            "127.0.0.1",
            self.port,
            "POST",
            run_path,
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "-1",
            },
        )
        self.assertEqual(status, 400)

        # malformed
        status, raw = _raw_request(
            "127.0.0.1",
            self.port,
            "POST",
            run_path,
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "abc",
            },
        )
        self.assertEqual(status, 400)

        # oversize
        big = b"x" * 5000
        status, raw = _raw_request(
            "127.0.0.1",
            self.port,
            "POST",
            run_path,
            body=big,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(big)),
            },
        )
        self.assertEqual(status, 413)

    def test_concurrent_run_409(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def slow_run(*_a, **_k):
            entered.set()
            release.wait(timeout=10)
            raise demo_server.classify_api.ClassifyError("LLM_API_KEY is not set")

        with mock.patch.object(demo_server, "run_api", side_effect=slow_run):
            results: list[tuple[int, dict]] = []

            def first() -> None:
                status, data, _ = _json_req(
                    f"{self.base}/api/run",
                    method="POST",
                    body={"tafsir": TAFSIR, "window": WINDOW},
                    headers={"Origin": "http://127.0.0.1"},
                )
                results.append((status, data))

            t = threading.Thread(target=first)
            t.start()
            self.assertTrue(entered.wait(timeout=5))
            status2, data2, _ = _json_req(
                f"{self.base}/api/run",
                method="POST",
                body={"tafsir": TAFSIR, "window": WINDOW},
                headers={"Origin": "http://127.0.0.1"},
            )
            self.assertEqual(status2, 409)
            self.assertIn("busy", (data2.get("error") or "").lower())
            release.set()
            t.join(timeout=10)
        self.assertTrue(results)
        self.assertEqual(results[0][0], 200)
        self.assertEqual(results[0][1].get("code"), "KEY_MISSING")

    def test_unsupported_methods_405(self) -> None:
        for method in ("PUT", "DELETE"):
            status, body = _raw_request("127.0.0.1", self.port, method, "/fahras.html")
            self.assertEqual(status, 405, method)

    def test_missing_key_fixed_code_no_leak(self) -> None:
        with mock.patch.dict(os.environ, {"LLM_API_KEY": ""}, clear=False):
            os.environ.pop("LLM_API_KEY", None)
            status, data, raw = _json_req(
                f"{self.base}/api/run",
                method="POST",
                body={"tafsir": TAFSIR, "window": WINDOW},
                headers={"Origin": "http://127.0.0.1"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(data.get("code"), "KEY_MISSING")
        self.assertIn("KEY_MISSING", data.get("error") or "")
        self.assertNotIn(SECRET, raw)
        self.assertNotIn("sk-", raw)
        self.assertNotIn("traceback", raw.lower())

    def test_exception_scrubs_key_from_response_and_stderr(self) -> None:
        with mock.patch.dict(os.environ, {"LLM_API_KEY": SECRET}, clear=False):

            def boom(*_a, **_k):
                raise RuntimeError(f"upstream exploded with {SECRET} in body")

            buf = io.StringIO()
            with mock.patch.object(demo_server, "run_api", side_effect=boom):
                with mock.patch.object(sys, "stderr", buf):
                    status, data, raw = _json_req(
                        f"{self.base}/api/run",
                        method="POST",
                        body={"tafsir": TAFSIR, "window": WINDOW},
                        headers={"Origin": "http://127.0.0.1"},
                    )
            self.assertEqual(status, 200)
            self.assertEqual(data.get("code"), "INTERNAL")
            self.assertNotIn(SECRET, raw)
            self.assertNotIn(SECRET, json.dumps(data))
            self.assertNotIn(SECRET, buf.getvalue())
            self.assertNotIn("upstream exploded", buf.getvalue())
            self.assertNotIn("Traceback", buf.getvalue())


class DemoServerFakeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _copy_minimal_tree(self.root)
        self._before_fake = _fake_dirs()
        self.httpd = demo_server.serve(
            port=0, root=self.root, fake=True, rebuild=False
        )
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._created_fake = _fake_dirs() - self._before_fake
        self._closed = False
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def tearDown(self) -> None:
        if not self._closed:
            self.httpd.shutdown()
            self.httpd.server_close()
            self._closed = True
        self._tmp.cleanup()

    def test_fake_run_writes_under_disposable_not_seed(self) -> None:
        status, health, _ = _json_req(f"{self.base}/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["fake"])
        status, data, _ = _json_req(
            f"{self.base}/api/run",
            method="POST",
            body={"tafsir": TAFSIR, "window": WINDOW},
            headers={"Origin": "http://127.0.0.1"},
        )
        self.assertEqual(status, 200, data)
        self.assertNotIn("error", data)
        self.assertEqual(data["annotator"], "demo-fake")
        self.assertGreaterEqual(data["moves"], 1)
        for key in (
            "auto_candidate",
            "specialist",
            "flags",
            "rejected_invalid_spans",
            "seconds",
        ):
            self.assertIn(key, data)
        # Seed root must stay untouched
        seed_moves = self.root / REL_BASE / "moves" / "demo-fake" / f"{WINDOW}.json"
        self.assertFalse(seed_moves.is_file(), seed_moves)
        # Disposable workspace received the write (discover via temp prefix, not _demo_state)
        self.assertTrue(self._created_fake)
        found = False
        for d in self._created_fake:
            cand = d / REL_BASE / "moves" / "demo-fake" / f"{WINDOW}.json"
            if cand.is_file():
                found = True
                break
        self.assertTrue(found, "demo-fake moves missing under disposable workspace")
        # Must not write into the real repo tree
        repo_moves = ROOT / REL_BASE / "moves" / "demo-fake" / f"{WINDOW}.json"
        self.assertFalse(repo_moves.is_file())

    def test_fake_workspace_cleaned_on_server_close(self) -> None:
        self.assertTrue(self._created_fake)
        for d in self._created_fake:
            self.assertTrue(d.exists(), d)
        self.httpd.shutdown()
        self.httpd.server_close()
        self._closed = True
        for d in self._created_fake:
            self.assertFalse(d.exists(), f"expected cleanup of {d}")


class DemoServerFakeRepoGuardTestCase(unittest.TestCase):
    """Fake mode against real ROOT must not mutate data/ or web/."""

    def test_fake_mode_leaves_repo_data_web_unchanged(self) -> None:
        data_before = _tree_hash(ROOT / "data")
        web_before = _tree_hash(ROOT / "web")
        before = _fake_dirs()
        with demo_server.serve(port=0, root=ROOT, fake=True, rebuild=True) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                status, data, _ = _json_req(
                    f"http://127.0.0.1:{port}/api/run",
                    method="POST",
                    body={"tafsir": TAFSIR, "window": WINDOW},
                    headers={"Origin": "http://127.0.0.1", "Host": f"127.0.0.1:{port}"},
                )
                self.assertEqual(status, 200, data)
                self.assertNotIn("error", data)
                self.assertEqual(data["annotator"], "demo-fake")
            finally:
                httpd.shutdown()
        created = _fake_dirs() - before
        self.assertFalse(created, f"leaked fake dirs: {created}")
        self.assertEqual(data_before, _tree_hash(ROOT / "data"))
        self.assertEqual(web_before, _tree_hash(ROOT / "web"))
        repo_moves = ROOT / REL_BASE / "moves" / "demo-fake" / f"{WINDOW}.json"
        self.assertFalse(repo_moves.is_file())

    def test_seed_failure_cleans_tmpdir(self) -> None:
        before = _fake_dirs()

        def boom(_root: Path):
            tmp = tempfile.TemporaryDirectory(prefix="tafsir-demo-fake-")
            # Simulate failure after TemporaryDirectory is created
            try:
                raise OSError("simulated seed failure")
            except Exception:
                tmp.cleanup()
                raise

        with mock.patch.object(demo_server, "seed_fake_workspace", side_effect=boom):
            with self.assertRaises(OSError):
                demo_server.serve(port=0, root=ROOT, fake=True, rebuild=False)
        leaked = _fake_dirs() - before
        self.assertFalse(leaked, f"leaked after seed failure: {leaked}")


if __name__ == "__main__":
    unittest.main()
