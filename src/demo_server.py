"""Local demo server: static web/ + /api/run (key stays in the process env).

Binds 127.0.0.1 only. Stdlib only. Reuses classify_api / run_window / v2_verify / build_fahras.
Demo UI is injected at request time from demo_inject.html — never written to disk.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
INJECT_PATH = SRC / "demo_inject.html"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import classify_api  # noqa: E402
import run_window  # noqa: E402
from build_fahras import build as build_fahras  # noqa: E402

DEFAULT_PORT = 8791
MAX_BODY = 4096
READ_TIMEOUT_S = 10
TAFSIR_RE = re.compile(r"^[a-z_]+$")
WINDOW_RE = re.compile(r"^[0-9]+_[0-9]+$")
FAKE_ANNOTATOR = "demo-fake"

FAKE_BANNER = (
    "\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
    "!!!  FAKE MODE — no network; annotator=demo-fake only   !!!\n"
    "!!!  For tests/screenshots — not a live model call      !!!\n"
    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
)

# Fixed client-facing messages only (no upstream/exception text).
ERROR_MESSAGES = {
    "KEY_MISSING": "المفتاح غير معيّن (KEY_MISSING)",
    "NETWORK": "تعذّر الاتصال بالخادم (NETWORK) — استخدم اللصق اليدوي",
    "INVALID_OUTPUT": "مخرجات النموذج غير صالحة (INVALID_OUTPUT)",
    "INTERNAL": "خطأ داخلي (INTERNAL)",
}


def scrub_secrets(text: str) -> str:
    """Remove API key material from any string that might be returned or printed."""
    out = text or ""
    key = os.environ.get("LLM_API_KEY") or ""
    if key:
        out = out.replace(key, "[REDACTED]")
    out = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", out)
    out = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[REDACTED]", out)
    return out


def is_local_host(value: str) -> bool:
    raw = (value or "").strip()
    if not raw:
        return False
    host = raw.lower()
    if "://" in host:
        host = urlparse(host).hostname or ""
    else:
        host = host.split("/")[0]
        if host.startswith("["):
            return False
        host = host.split(":")[0]
    return host in ("127.0.0.1", "localhost")


def packet_allowlist(root: Path) -> set[tuple[str, str]]:
    allowed: set[tuple[str, str]] = set()
    for key, rel in run_window.TAFSIR_BASES.items():
        pkt_dir = root / rel / "packets"
        if not pkt_dir.is_dir():
            continue
        for path in pkt_dir.glob("*.json"):
            allowed.add((key, path.stem))
    return allowed


def resolve_base(root: Path, tafsir: str) -> Path:
    key = (tafsir or "").strip()
    if key in run_window.TAFSIR_BASES:
        return root / run_window.TAFSIR_BASES[key]
    multi = root / "data" / "multi" / key
    if multi.is_dir():
        return multi
    raise ValueError(f"unknown tafsir {tafsir!r}")


def resolve_packet(base: Path, window: str) -> tuple[Path, str]:
    """Map UI window id (e.g. 2_255) to packet file; allow *_tafsir stems."""
    candidates = [window]
    if not window.endswith("_tafsir"):
        candidates.append(f"{window}_tafsir")
    for stem in candidates:
        path = base / "packets" / f"{stem}.json"
        if path.is_file():
            return path, stem
    raise FileNotFoundError(f"packet not found for window {window!r}")


def window_stems(window: str) -> list[str]:
    stems = [window]
    if not window.endswith("_tafsir"):
        stems.append(f"{window}_tafsir")
    return stems


def count_rejected_invalid_spans(verified_payload: dict) -> int:
    n = 0
    for move in verified_payload.get("moves") or []:
        flags = move.get("flags") or []
        if not move.get("span_ids"):
            n += 1
            continue
        if any(str(f).startswith("unknown_span") for f in flags):
            n += 1
    return n


def find_donor_moves(base: Path, window_stem: str) -> Path:
    moves_root = base / "moves"
    if not moves_root.is_dir():
        raise FileNotFoundError("no moves directory for fake donor")
    for ann_dir in sorted(moves_root.iterdir()):
        if not ann_dir.is_dir() or ann_dir.name == FAKE_ANNOTATOR:
            continue
        cand = ann_dir / f"{window_stem}.json"
        if cand.is_file():
            return cand
    raise FileNotFoundError(f"no donor moves for window {window_stem}")


def run_fake(base: Path, window_stem: str) -> dict[str, Any]:
    donor = find_donor_moves(base, window_stem)
    payload = json.loads(donor.read_bytes().decode("utf-8"))
    cleaned = classify_api.sanitize_moves_payload(payload, window_stem)
    path = classify_api.write_moves(base / "moves", FAKE_ANNOTATOR, window_stem, cleaned)
    verified = run_window.run_verifier(base, FAKE_ANNOTATOR, window_stem, cleaned)
    return {
        "annotator": FAKE_ANNOTATOR,
        "path": path,
        "payload": cleaned,
        "verified": verified,
    }


def run_api(base: Path, packet_path: Path, window_stem: str) -> dict[str, Any]:
    model, base_url = classify_api.resolve_env()
    if not (os.environ.get("LLM_API_KEY") or "").strip():
        raise classify_api.ClassifyError("LLM_API_KEY is not set")
    if not model:
        raise classify_api.ClassifyError("LLM_MODEL is not set")
    if not base_url:
        raise classify_api.ClassifyError("LLM_BASE_URL is not set")
    result = classify_api.classify(packet_path, model, base_url, base / "moves")
    verified = run_window.run_verifier(
        base, result["annotator"], window_stem, result["payload"]
    )
    result["verified"] = verified
    return result


def summary_response(result: dict[str, Any], seconds: float) -> dict[str, Any]:
    verified = result["verified"]
    summary = verified["summary"]
    return {
        "moves": summary["move_count"],
        "auto_candidate": summary["auto_candidate"],
        "specialist": summary["specialist"],
        "flags": summary["flag_count"],
        "rejected_invalid_spans": count_rejected_invalid_spans(verified),
        "annotator": result["annotator"],
        "seconds": round(seconds, 3),
    }


def map_exception_to_error(exc: BaseException) -> dict[str, str]:
    """Map any exception to fixed code + Arabic message (never echo upstream text)."""
    raw = scrub_secrets(str(exc) or "")
    low = raw.lower()
    code = "INTERNAL"
    if isinstance(exc, classify_api.ClassifyError):
        http_m = re.search(r"\bhttp\s+(\d{3})\b", low)
        if "llm_api_key" in low or ("api_key" in low and "not set" in low):
            code = "KEY_MISSING"
        elif "network" in low or "urlerror" in low:
            code = "NETWORK"
        elif http_m:
            code = f"HTTP_{http_m.group(1)}"
        elif any(
            tok in low
            for tok in (
                "json",
                "empty model",
                "not a json",
                "unexpected",
                "invalid",
                "sanitize",
                "reply",
                "no spans",
            )
        ):
            code = "INVALID_OUTPUT"
        elif "llm_model" in low or "llm_base_url" in low or "base_url" in low:
            code = "KEY_MISSING"
    if code.startswith("HTTP_"):
        msg = f"خطأ من الخادم ({code})"
    else:
        msg = ERROR_MESSAGES.get(code, ERROR_MESSAGES["INTERNAL"])
    return {"error": msg, "code": code}


def path_inside_web(web_dir: Path, url_path: str) -> Path | None:
    """Resolve URL path under web_dir; None if traversal / escape / ADS / missing."""
    decoded = unquote(url_path or "")
    if "\x00" in decoded:
        return None
    normalized = decoded.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None
    # Reject Windows ADS / stream / drive-letter segments (colon in any part)
    if any(":" in p for p in parts):
        return None
    rel = "/".join(parts)
    if not rel:
        return None
    web_root = os.path.realpath(str(web_dir))
    candidate = os.path.realpath(os.path.join(web_root, rel.replace("/", os.sep)))
    try:
        if os.path.commonpath([web_root, candidate]) != web_root:
            return None
    except ValueError:
        return None
    return Path(candidate)


def load_inject_html() -> str:
    if not INJECT_PATH.is_file():
        raise SystemExit(f"missing inject snippet: {INJECT_PATH}")
    return INJECT_PATH.read_text(encoding="utf-8")


def inject_demo_html(page_html: str, inject: str) -> str:
    """Insert demo snippet before </body>; append if no body close tag."""
    lower = page_html.lower()
    idx = lower.rfind("</body>")
    if idx < 0:
        return page_html + "\n" + inject
    return page_html[:idx] + inject + "\n" + page_html[idx:]


def seed_fake_workspace(source_root: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Disposable copy of data/ + web/ so fake mode never writes the repo tree."""
    tmp = tempfile.TemporaryDirectory(prefix="tafsir-demo-fake-")
    try:
        dest = Path(tmp.name)
        src_data = source_root / "data"
        src_web = source_root / "web"
        if src_data.is_dir():
            shutil.copytree(src_data, dest / "data")
        if src_web.is_dir():
            shutil.copytree(src_web, dest / "web")
        else:
            (dest / "web").mkdir(parents=True, exist_ok=True)
        return tmp, dest
    except Exception:
        try:
            tmp.cleanup()
        except Exception:  # noqa: BLE001
            pass
        raise


class DemoState:
    def __init__(self, root: Path, *, fake: bool = False, rebuild: bool = True) -> None:
        self.source_root = root
        self.fake = fake
        self.rebuild = rebuild
        self.lock = threading.Lock()
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self.inject_html = load_inject_html()
        if fake:
            try:
                self._tmpdir, self.root = seed_fake_workspace(root)
                self.web_dir = self.root / "web"
            except Exception:
                self.cleanup()
                raise
        else:
            self.root = root
            self.web_dir = root / "web"
        self.allowlist = packet_allowlist(self.root)

    def cleanup(self) -> None:
        tmp = self._tmpdir
        self._tmpdir = None
        if tmp is not None:
            try:
                tmp.cleanup()
            except Exception:  # noqa: BLE001
                pass


class DemoHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that cleans the fake workspace on server_close."""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[SimpleHTTPRequestHandler],
        state: DemoState,
    ) -> None:
        self._demo_state = state
        super().__init__(server_address, RequestHandlerClass)

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            state = self._demo_state
            self._demo_state = None  # type: ignore[assignment]
            if state is not None:
                state.cleanup()

    def __enter__(self) -> DemoHTTPServer:
        return self

    def __exit__(self, *exc: object) -> bool:
        try:
            self.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.server_close()
        return False


def make_handler(state: DemoState) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(state.web_dir), **kwargs)

        def log_message(self, fmt: str, *args: Any) -> None:
            msg = scrub_secrets(fmt % args if args else fmt)
            sys.stderr.write("%s - %s\n" % (self.address_string(), msg))

        def _send_json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _local_ok(self) -> bool:
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin", "")
            if host and not is_local_host(host):
                return False
            if origin and not is_local_host(origin):
                return False
            return bool(host)

        def _send_bytes(
            self, code: int, body: bytes, content_type: str
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _serve_fahras_injected(self) -> None:
            path = path_inside_web(state.web_dir, "/fahras.html")
            if path is None or not path.is_file():
                self.send_error(404, "File not found")
                return
            html = path.read_bytes().decode("utf-8")
            html = inject_demo_html(html, state.inject_html)
            self._send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")

        def _serve_static(self, url_path: str) -> None:
            target = path_inside_web(state.web_dir, url_path)
            if target is None or not target.is_file():
                self.send_error(404, "File not found")
                return
            # Re-check containment after open (TOCTOU defence)
            try:
                real = os.path.realpath(str(target))
                web_root = os.path.realpath(str(state.web_dir))
                if os.path.commonpath([web_root, real]) != web_root:
                    self.send_error(404, "File not found")
                    return
            except ValueError:
                self.send_error(404, "File not found")
                return
            data = Path(real).read_bytes()
            ctype = self.guess_type(real)
            self._send_bytes(200, data, ctype)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/health":
                if not self._local_ok():
                    self._send_json(403, {"error": "forbidden: local Host/Origin only"})
                    return
                key_present = bool((os.environ.get("LLM_API_KEY") or "").strip())
                model = os.environ.get("LLM_MODEL") or None
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "key_present": key_present,
                        "model": model,
                        "fake": bool(state.fake),
                    },
                )
                return
            # Special HTML route: ONLY exact "/" and "/fahras.html" (inject demo UI)
            if path in ("/", "/fahras.html"):
                self._serve_fahras_injected()
                return
            # All other static paths: contain under web/ or 404
            self._serve_static(path)

        def do_PUT(self) -> None:  # noqa: N802
            self.send_error(405, "Method Not Allowed")

        def do_DELETE(self) -> None:  # noqa: N802
            self.send_error(405, "Method Not Allowed")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/run":
                self.send_error(404, "not found")
                return
            if not self._local_ok():
                self._send_json(403, {"error": "forbidden: local Host/Origin only"})
                return
            raw_cl = self.headers.get("Content-Length")
            if raw_cl is None or str(raw_cl).strip() == "":
                self._send_json(400, {"error": "missing Content-Length"})
                return
            try:
                length = int(str(raw_cl).strip())
            except (TypeError, ValueError):
                self._send_json(400, {"error": "invalid Content-Length"})
                return
            if length <= 0:
                self._send_json(400, {"error": "invalid Content-Length"})
                return
            if length > MAX_BODY:
                self._send_json(413, {"error": "payload too large"})
                return
            try:
                self.connection.settimeout(READ_TIMEOUT_S)
                raw = self.rfile.read(length)
            except OSError:
                self._send_json(400, {"error": "read timeout or truncated body"})
                return
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"error": "invalid JSON body"})
                return
            if not isinstance(body, dict):
                self._send_json(400, {"error": "invalid JSON body"})
                return
            tafsir = str(body.get("tafsir") or "").strip()
            window = str(body.get("window") or "").strip()
            if not TAFSIR_RE.match(tafsir) or not WINDOW_RE.match(window):
                self._send_json(400, {"error": "invalid tafsir or window"})
                return
            # Allowlist + permitted stem BEFORE any filesystem path construction
            window_stem = next(
                (s for s in window_stems(window) if (tafsir, s) in state.allowlist),
                None,
            )
            if window_stem is None:
                self._send_json(400, {"error": "window not in packet allowlist"})
                return
            try:
                base = resolve_base(state.root, tafsir)
            except ValueError:
                self._send_json(400, {"error": "window not in packet allowlist"})
                return
            packet_path = base / "packets" / f"{window_stem}.json"
            if not packet_path.is_file():
                self._send_json(400, {"error": "window not in packet allowlist"})
                return
            if not state.lock.acquire(blocking=False):
                self._send_json(409, {"error": "busy: one run at a time"})
                return
            started = time.time()
            try:
                if state.fake:
                    result = run_fake(base, window_stem)
                else:
                    result = run_api(base, packet_path, window_stem)
                # Real runs may rebuild the real web/; fake mode never touches repo web/
                if (
                    state.rebuild
                    and not state.fake
                    and state.source_root == ROOT
                ):
                    build_fahras()
                self._send_json(200, summary_response(result, time.time() - started))
            except classify_api.ClassifyError as e:
                payload = map_exception_to_error(e)
                _log_safe_error(payload["code"], tafsir, window)
                self._send_json(200, payload)
            except Exception as e:  # noqa: BLE001
                payload = map_exception_to_error(e)
                _log_safe_error(payload["code"], tafsir, window)
                self._send_json(200, payload)
            finally:
                state.lock.release()

    return Handler


def _log_safe_error(code: str, tafsir: str, window: str) -> None:
    """Sanitized, bounded log — no traceback, no upstream body, no env."""
    t = scrub_secrets(re.sub(r"[^a-z0-9_]", "", (tafsir or "")[:64]))
    w = scrub_secrets(re.sub(r"[^0-9_]", "", (window or "")[:32]))
    c = scrub_secrets(re.sub(r"[^A-Z0-9_]", "", (code or "")[:32]))
    sys.stderr.write(f"demo_server error code={c} tafsir={t} window={w}\n")


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    root: Path | None = None,
    fake: bool = False,
    rebuild: bool = True,
) -> DemoHTTPServer:
    if host not in ("127.0.0.1", "localhost"):
        raise SystemExit("demo_server binds 127.0.0.1 only (refusing other hosts)")
    bind_host = "127.0.0.1"
    state = DemoState(root or ROOT, fake=fake, rebuild=rebuild)
    try:
        if not state.web_dir.is_dir():
            raise SystemExit(f"missing web dir: {state.web_dir}")
        if fake:
            print(FAKE_BANNER, flush=True)
        handler = make_handler(state)
        httpd = DemoHTTPServer((bind_host, port), handler, state)
    except Exception:
        state.cleanup()
        raise
    print(
        f"demo_server: http://127.0.0.1:{port}/fahras.html "
        f"fake={fake} key_present={bool((os.environ.get('LLM_API_KEY') or '').strip())}",
        flush=True,
    )
    return httpd


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Local demo server for live AI run button")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument(
        "--fake",
        action="store_true",
        help="no network; copy donor moves → demo-fake (tests/screenshots)",
    )
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="project root override (tests: temp copy; default: repo root)",
    )
    p.add_argument(
        "--no-rebuild",
        action="store_true",
        help="skip build_fahras after a run (tests)",
    )
    args = p.parse_args(argv)
    root = args.root.resolve() if args.root else ROOT
    httpd = serve(
        port=args.port,
        root=root,
        fake=args.fake,
        rebuild=not args.no_rebuild,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\ndemo_server: stopped", flush=True)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
