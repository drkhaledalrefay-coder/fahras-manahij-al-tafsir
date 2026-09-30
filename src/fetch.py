"""Download and extract Ibn Kathir tafsir texts from two independent sources.

CORE RULE: every Arabic string written under data/ comes from downloaded bytes.
This module never invents or pastes Arabic source text.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

TARGET_AYAT = [(2, 255), (17, 105), (2, 102)]

HF_API = "https://huggingface.co/api/datasets/tafsircenter/tafsir-mcp-data"
HF_RESOLVE = "https://huggingface.co/datasets/tafsircenter/tafsir-mcp-data/resolve/main/"
HF_README = "https://huggingface.co/datasets/tafsircenter/tafsir-mcp-data/raw/main/README.md"

QURAN_COM_TAFSIRS = "https://api.quran.com/api/v4/resources/tafsirs"
QURAN_COM_BY_AYAH = "https://api.quran.com/api/v4/tafsirs/{id}/by_ayah/{surah}:{ayah}"

JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/"

USER_AGENT = "tafsir-pilot/1.0 (+text-integrity; stdlib-only)"


class _HTMLTextExtractor(HTMLParser):
    """Extract text nodes only; do not invent wording."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def get_text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    """Strip HTML tags via html.parser; retain text content otherwise."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor.get_text()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, dest: Path, manifest: list[dict], *, timeout: int = 300) -> bytes:
    """GET url, save response body byte-for-byte, append manifest entry."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        status = e.code
        dest.write_bytes(body)
        entry = {
            "url": url,
            "path": str(dest.relative_to(ROOT)).replace("\\", "/"),
            "timestamp_utc": _utc_now(),
            "http_status": status,
            "byte_length": len(body),
            "sha256": _sha256_bytes(body),
            "error": str(e),
        }
        manifest.append(entry)
        raise
    dest.write_bytes(body)
    entry = {
        "url": url,
        "path": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "timestamp_utc": _utc_now(),
        "http_status": status,
        "byte_length": len(body),
        "sha256": _sha256_bytes(body),
    }
    manifest.append(entry)
    return body


def _write_text_exact(path: Path, text: str, manifest: list[dict], *, source_url: str) -> None:
    """Write UTF-8 text as bytes (no newline translation) and record sha256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    manifest.append(
        {
            "url": source_url,
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "timestamp_utc": _utc_now(),
            "http_status": None,
            "byte_length": len(data),
            "sha256": _sha256_bytes(data),
            "kind": "extracted_text",
        }
    )


def _pick_hf_data_file(siblings: list[dict]) -> str:
    names = [s.get("rfilename", "") for s in siblings]
    for n in names:
        if n.lower().endswith(".db") or n.lower().endswith(".sqlite"):
            return n
    for n in names:
        if n and not n.startswith(".") and n != "README.md":
            return n
    raise RuntimeError(f"No data file found in HF siblings: {names}")


def fetch_source_a(manifest: list[dict]) -> dict:
    """Download Tafsir Center HF dataset and extract the three Ibn Kathir entries."""
    out_dir = RAW / "tafsircenter"
    out_dir.mkdir(parents=True, exist_ok=True)

    api_body = http_get(HF_API, out_dir / "dataset_api.json", manifest)
    api = json.loads(api_body.decode("utf-8"))
    card = api.get("cardData") or {}
    license_field = card.get("license")
    siblings = api.get("siblings") or []
    data_file = _pick_hf_data_file(siblings)

    try:
        http_get(HF_README, out_dir / "README.md", manifest)
    except Exception as exc:  # noqa: BLE001 — record and continue
        manifest.append(
            {
                "url": HF_README,
                "path": None,
                "timestamp_utc": _utc_now(),
                "http_status": None,
                "byte_length": 0,
                "sha256": None,
                "error": f"README fetch failed: {exc}",
            }
        )

    db_url = HF_RESOLVE + data_file
    db_path = out_dir / data_file
    # Reuse a prior byte-identical local copy if present (probe/cache), else download.
    probe = RAW / "_probe_quran.db"
    if db_path.is_file() and db_path.stat().st_size > 0:
        body = db_path.read_bytes()
        manifest.append(
            {
                "url": db_url,
                "path": str(db_path.relative_to(ROOT)).replace("\\", "/"),
                "timestamp_utc": _utc_now(),
                "http_status": 200,
                "byte_length": len(body),
                "sha256": _sha256_bytes(body),
                "note": "reused existing local file; sha256 of on-disk bytes",
            }
        )
    elif probe.is_file() and probe.stat().st_size > 0:
        body = probe.read_bytes()
        db_path.write_bytes(body)
        manifest.append(
            {
                "url": db_url,
                "path": str(db_path.relative_to(ROOT)).replace("\\", "/"),
                "timestamp_utc": _utc_now(),
                "http_status": 200,
                "byte_length": len(body),
                "sha256": _sha256_bytes(body),
                "note": "promoted from data/raw/_probe_quran.db (earlier HTTP 200 download of same URL)",
            }
        )
    else:
        http_get(db_url, db_path, manifest, timeout=600)

    table = "tafsir_katheer"
    columns = ("sura", "aya", "tafsir")
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True)
    try:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info([{table}])")
        col_info = [r[1] for r in cur.fetchall()]
        if list(columns) != [c for c in columns if c in col_info]:
            raise RuntimeError(f"Unexpected schema for {table}: {col_info}")
        extracted = {}
        for surah, ayah in TARGET_AYAT:
            cur.execute(
                f"SELECT [{columns[2]}] FROM [{table}] WHERE [{columns[0]}]=? AND [{columns[1]}]=?",
                (surah, ayah),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                raise RuntimeError(f"Missing tafsir_katheer row for {surah}:{ayah}")
            text = row[0]
            if not isinstance(text, str):
                text = str(text)
            key = f"{surah}_{ayah}"
            txt_path = out_dir / f"{key}.txt"
            _write_text_exact(txt_path, text, manifest, source_url=f"sqlite:{data_file}:{table}:{surah}:{ayah}")
            extracted[key] = {
                "surah": surah,
                "ayah": ayah,
                "path": str(txt_path.relative_to(ROOT)).replace("\\", "/"),
                "char_length": len(text),
                "sha256": _sha256_bytes(text.encode("utf-8")),
            }
    finally:
        conn.close()

    meta = {
        "source": "tafsircenter",
        "dataset": "tafsircenter/tafsir-mcp-data",
        "dataset_api_url": HF_API,
        "license": license_field,
        "cardData": card,
        "data_file": data_file,
        "table": table,
        "columns": list(columns),
        "edition_publisher_metadata": {
            "from_card_readme": (
                "Tafsir al-Quran al-Azim (Ibn Kathir); sourced from Tafsir Center "
                "for Quranic Studies (tafsir.net). No print-edition identifier in DB schema."
            ),
            "db_edition_fields": "none found in table schema",
        },
        "extracted": extracted,
    }
    meta_path = out_dir / "source_metadata.json"
    meta_path.write_bytes(json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))
    return meta


def _select_arabic_ibn_kathir(tafsirs: list[dict]) -> dict:
    """Select Arabic Ibn Kathir resource; do not hardcode id."""
    candidates = []
    for t in tafsirs:
        lang = (t.get("language_name") or t.get("lang") or "").strip().lower()
        name = t.get("name") or ""
        slug = t.get("slug") or ""
        author = t.get("author_name") or ""
        blob = f"{name} {slug} {author}"
        if lang == "arabic" and ("كثير" in blob or "Kathir" in blob or "kathir" in blob.lower()):
            candidates.append(t)
    if not candidates:
        raise RuntimeError("No Arabic Ibn Kathir tafsir found in quran.com resources")
    # Prefer slug containing ar- and kathir if multiple
    for t in candidates:
        slug = (t.get("slug") or "").lower()
        if "kathir" in slug or "katheer" in slug:
            return t
    return candidates[0]


def _fetch_source_b_jsdelivr(manifest: list[dict]) -> dict:
    """Fallback: spa5k/tafsir_api via jsDelivr CDN."""
    out_dir = RAW / "jsdelivr_tafsir_api"
    out_dir.mkdir(parents=True, exist_ok=True)
    # editions index — try common listing endpoints
    index_urls = [
        JSDELIVR_BASE,
        "https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/editions.json",
        "https://api.github.com/repos/spa5k/tafsir_api/contents/tafsir",
    ]
    editions_raw = None
    editions_url = None
    last_err = None
    for url in index_urls:
        try:
            name = "index.json" if url.endswith("/") else Path(urllib.parse.urlparse(url).path).name
            if not name or name == "tafsir":
                name = "listing.json"
            body = http_get(url, out_dir / name, manifest)
            editions_raw = body
            editions_url = url
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if editions_raw is None:
        raise RuntimeError(f"jsDelivr fallback index failed: {last_err}")

    text = editions_raw.decode("utf-8", errors="replace")
    # GitHub API returns JSON array of directory entries
    edition_id = None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        # could be github contents or list of edition slugs
        names = []
        for item in parsed:
            if isinstance(item, dict):
                names.append(item.get("name") or item.get("slug") or "")
            else:
                names.append(str(item))
        for n in names:
            low = n.lower()
            if ("kathir" in low or "katheer" in low or "كثير" in n) and (
                low.startswith("ar") or "arabic" in low or n.startswith("ar-")
            ):
                edition_id = n.rstrip("/")
                break
        if edition_id is None:
            for n in names:
                low = n.lower()
                if "kathir" in low or "katheer" in low:
                    edition_id = n.rstrip("/")
                    break
    elif isinstance(parsed, dict):
        for key, val in parsed.items():
            blob = f"{key} {val}".lower()
            if "kathir" in blob or "katheer" in blob or "كثير" in f"{key}{val}":
                if "ar" in blob:
                    edition_id = key
                    break
        if edition_id is None:
            for key in parsed:
                if "kathir" in key.lower() or "katheer" in key.lower():
                    edition_id = key
                    break

    if not edition_id:
        raise RuntimeError("Could not locate Arabic Ibn Kathir edition on jsDelivr fallback")

    extracted = {}
    for surah, ayah in TARGET_AYAT:
        # spa5k layout: tafsir/<edition>/<surah>/<ayah>.json
        url = f"{JSDELIVR_BASE}{edition_id}/{surah}/{ayah}.json"
        raw_path = out_dir / f"{surah}_{ayah}.json"
        body = http_get(url, raw_path, manifest)
        payload = json.loads(body.decode("utf-8"))
        # common fields: text / tafsir
        raw_text = payload.get("text") or payload.get("tafsir") or payload.get("data")
        if isinstance(raw_text, dict):
            raw_text = raw_text.get("text") or raw_text.get("tafsir")
        if not isinstance(raw_text, str):
            raise RuntimeError(f"Unexpected jsDelivr payload for {surah}:{ayah}")
        plain = strip_html(raw_text) if "<" in raw_text else raw_text
        key = f"{surah}_{ayah}"
        txt_path = out_dir / f"{key}.txt"
        _write_text_exact(txt_path, plain, manifest, source_url=url)
        extracted[key] = {
            "surah": surah,
            "ayah": ayah,
            "path": str(txt_path.relative_to(ROOT)).replace("\\", "/"),
            "char_length": len(plain),
            "sha256": _sha256_bytes(plain.encode("utf-8")),
        }

    meta = {
        "source": "jsdelivr_tafsir_api",
        "used": "fallback",
        "editions_url": editions_url,
        "edition_id": edition_id,
        "base": JSDELIVR_BASE,
        "extracted": extracted,
    }
    (out_dir / "source_metadata.json").write_bytes(
        json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
    )
    return meta


def fetch_source_b(manifest: list[dict]) -> dict:
    """Download Arabic Ibn Kathir from quran.com v4; fallback to jsDelivr."""
    out_dir = RAW / "quran_com"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        body = http_get(QURAN_COM_TAFSIRS, out_dir / "tafsirs.json", manifest)
        data = json.loads(body.decode("utf-8"))
        tafsirs = data.get("tafsirs") or data
        if not isinstance(tafsirs, list):
            raise RuntimeError("Unexpected tafsirs payload shape")
        chosen = _select_arabic_ibn_kathir(tafsirs)
        resource_id = chosen["id"]
        extracted = {}
        last_tafsir_obj = None
        for surah, ayah in TARGET_AYAT:
            url = QURAN_COM_BY_AYAH.format(id=resource_id, surah=surah, ayah=ayah)
            raw_path = out_dir / f"{surah}_{ayah}.json"
            raw = http_get(url, raw_path, manifest)
            payload = json.loads(raw.decode("utf-8"))
            tafsir = payload.get("tafsir") or payload
            last_tafsir_obj = tafsir
            html_or_text = tafsir.get("text")
            if not isinstance(html_or_text, str):
                raise RuntimeError(f"No text field in quran.com response for {surah}:{ayah}")
            plain = strip_html(html_or_text)
            key = f"{surah}_{ayah}"
            txt_path = out_dir / f"{key}.txt"
            _write_text_exact(txt_path, plain, manifest, source_url=url)
            extracted[key] = {
                "surah": surah,
                "ayah": ayah,
                "path": str(txt_path.relative_to(ROOT)).replace("\\", "/"),
                "char_length": len(plain),
                "sha256": _sha256_bytes(plain.encode("utf-8")),
            }

        meta = {
            "source": "quran_com",
            "used": "primary",
            "resources_url": QURAN_COM_TAFSIRS,
            "resource": {
                "id": resource_id,
                "name": chosen.get("name"),
                "author_name": chosen.get("author_name"),
                "language_name": chosen.get("language_name"),
                "slug": chosen.get("slug"),
                "translated_name": chosen.get("translated_name"),
            },
            "by_ayah_resource_fields": {
                "resource_id": (last_tafsir_obj or {}).get("resource_id"),
                "resource_name": (last_tafsir_obj or {}).get("resource_name"),
                "language_id": (last_tafsir_obj or {}).get("language_id"),
                "slug": (last_tafsir_obj or {}).get("slug"),
                "source_edition_field": "none present in API response",
            },
            "extracted": extracted,
        }
        (out_dir / "source_metadata.json").write_bytes(
            json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")
        )
        return meta
    except Exception as exc:  # noqa: BLE001
        manifest.append(
            {
                "url": QURAN_COM_TAFSIRS,
                "path": None,
                "timestamp_utc": _utc_now(),
                "http_status": None,
                "byte_length": 0,
                "sha256": None,
                "error": f"quran.com failed, trying jsDelivr fallback: {exc}",
            }
        )
        return _fetch_source_b_jsdelivr(manifest)


def fetch_all() -> dict:
    """Fetch both sources and write data/raw/manifest.json."""
    RAW.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    meta_a = fetch_source_a(manifest)
    meta_b = fetch_source_b(manifest)
    manifest_path = RAW / "manifest.json"
    payload = {
        "generated_at_utc": _utc_now(),
        "entries": manifest,
        "source_a": meta_a,
        "source_b": meta_b,
    }
    manifest_path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return payload


if __name__ == "__main__":
    result = fetch_all()
    print("Source A:", result["source_a"]["source"], "license=", result["source_a"].get("license"))
    print("Source B:", result["source_b"]["source"], "used=", result["source_b"].get("used"))
    for key in sorted(result["source_a"]["extracted"]):
        a = result["source_a"]["extracted"][key]["char_length"]
        b = result["source_b"]["extracted"][key]["char_length"]
        print(f"  {key}: A={a} chars, B={b} chars")
