"""Build web/methods.html from src/methods_template.html + v2 JSON data."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "methods_template.html"
OUT = ROOT / "web" / "methods.html"
WINDOWS_DIR = ROOT / "data" / "v2" / "windows"
MARKERS_DIR = ROOT / "data" / "v2" / "markers"
VERIFIED_DIR = ROOT / "data" / "v2" / "verified"

DATA_MARKER = "__METHODS_DATA_JSON__"

WINDOW_IDS = ("2_255_tafsir", "17_105", "2_102")


def embed(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def collect_data() -> dict:
    windows = {}
    markers = {}
    for wid in WINDOW_IDS:
        wpath = WINDOWS_DIR / f"{wid}.json"
        mpath = MARKERS_DIR / f"{wid}.json"
        if not wpath.is_file():
            raise SystemExit(f"missing window {wid} — run v2_windows.py")
        if not mpath.is_file():
            raise SystemExit(f"missing markers {wid} — run v2_markers.py")
        w = _read_json(wpath)
        # Drop full window_text duplication risk — keep it; UI needs it
        windows[wid] = {
            "window_id": w["window_id"],
            "ayah": w["ayah"],
            "surah": w.get("surah"),
            "ayah_number": w.get("ayah_number"),
            "source_file": w["source_file"],
            "source_sha256": w.get("source_sha256"),
            "window_start": w["window_start"],
            "window_end": w["window_end"],
            "window_text": w["window_text"],
            "spans": w["spans"],
            "apparatus": w.get("apparatus") or [],
            "selection": w.get("selection") or {},
        }
        m = _read_json(mpath)
        markers[wid] = {
            "family_counts": m.get("family_counts") or {},
            "spans": m.get("spans") or [],
            "editor_footnote_evidence": m.get("editor_footnote_evidence") or [],
            "isnad_ranges": m.get("isnad_ranges") or [],
        }

    verified: dict = {}
    classifier_ran = False
    if VERIFIED_DIR.is_dir():
        for ann_dir in sorted(p for p in VERIFIED_DIR.iterdir() if p.is_dir()):
            # Skip fixture annotator in UI
            if ann_dir.name == "fixture":
                continue
            for path in sorted(ann_dir.glob("*.json")):
                classifier_ran = True
                payload = _read_json(path)
                verified.setdefault(path.stem, {})[ann_dir.name] = {
                    "annotator": ann_dir.name,
                    "moves": payload.get("moves") or [],
                    "summary": payload.get("summary") or {},
                }

    return {
        "windows": windows,
        "markers": markers,
        "verified": verified,
        "classifier_ran": classifier_ran,
        "default_window": "2_255_tafsir",
        "tafsir": {
            "id": "ibn_kathir",
            "name": "تفسير ابن كثير",
        },
        "window_labels": {
            "2_255_tafsir": "آية الكرسي",
            "17_105": "الإسراء ١٠٥",
            "2_102": "البقرة ١٠٢",
        },
    }


def check_html(html: str) -> None:
    if not html.startswith('<meta charset="utf-8">'):
        raise SystemExit("methods.html must start with charset meta")
    if "\r" in html:
        raise SystemExit("methods.html must use LF newlines")
    lowered = html.lower()
    # Exact document shells only — do not trip on <header>.
    for token in ("<!doctype", "<html", "</html", "<head>", "<head ", "</head", "<body", "</body"):
        if token in lowered:
            raise SystemExit(f"forbidden markup: {token}")
    urls = re.findall(r"(?:href|src)\s*=\s*[\"'](https?://[^\"']+)", html, flags=re.I)
    urls += re.findall(r"url\(\s*[\"']?(https?://[^)\"']+)", html, flags=re.I)
    bad = [url for url in urls if "fonts.googleapis.com" not in url]
    if bad:
        raise SystemExit("unexpected external URL: " + ", ".join(bad))
    if "fonts.googleapis.com" not in html:
        raise SystemExit("missing Google Fonts stylesheet")
    if DATA_MARKER in html:
        raise SystemExit("data marker not replaced")

    # Side-stripe borders wider than 1px
    stripe = re.findall(
        r"border-(?:inline-start|inline-end|left|right)\s*:\s*([0-9.]+)px",
        html,
        flags=re.I,
    )
    wide = [x for x in stripe if float(x) > 1]
    if wide:
        raise SystemExit(f"side-stripe borders >1px found: {wide}")


def build() -> Path:
    if not TEMPLATE.is_file():
        raise SystemExit(f"missing template {TEMPLATE}")
    data = collect_data()
    html = TEMPLATE.read_bytes().decode("utf-8")
    if "\r\n" in html:
        html = html.replace("\r\n", "\n")
    if DATA_MARKER not in html:
        raise SystemExit("template missing data marker")
    html = html.replace(DATA_MARKER, embed(data))
    check_html(html)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(html.encode("utf-8"))
    print(
        f"wrote {OUT.relative_to(ROOT).as_posix()} "
        f"({OUT.stat().st_size} bytes) classifier_ran={data['classifier_ran']}"
    )
    return OUT


if __name__ == "__main__":
    build()
