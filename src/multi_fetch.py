"""Extract pinned verse texts for additional tafsirs from a local quran.db.

Deterministic, offline, read-only SQLite. Does not touch Ibn Kathir files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from textcore import sha256_bytes as _sha256_bytes
RAW = ROOT / "data" / "raw"
MANIFEST_PATH = RAW / "manifest.json"

TARGET_AYAT = [(2, 255), (2, 102), (17, 105)]

# tafsir_id → SQLite table name
SOURCES = {
    "al_tabari": "tafsir_tabary",
    "al_saadi": "tafsir_saadi",
    "al_baghawi": "tafsir_baghawy",
}

EXPECTED_DB_SHA256 = "10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27"




def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"generated_at_utc": _utc_now(), "entries": []}
    return json.loads(MANIFEST_PATH.read_bytes().decode("utf-8"))


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    )


def _entry_for_path(manifest: dict, rel_path: str) -> dict | None:
    for e in manifest.get("entries") or []:
        if e.get("path") == rel_path:
            return e
    return None


def _verify_db(db_path: Path) -> str:
    if not db_path.is_file():
        raise SystemExit(f"DB not found: {db_path}")
    digest = _sha256_bytes(db_path.read_bytes())
    if digest != EXPECTED_DB_SHA256:
        raise SystemExit(
            f"DB sha256 mismatch:\n  got      {digest}\n  expected {EXPECTED_DB_SHA256}"
        )
    return digest


def extract(db_path: Path) -> dict:
    db_sha = _verify_db(db_path)
    print(f"DB ok sha256={db_sha[:12]}…")

    manifest = _load_manifest()
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    summary: dict = {"db_sha256": db_sha, "extracted": {}}
    try:
        cur = conn.cursor()
        for tafsir_id, table in SOURCES.items():
            cur.execute(f"PRAGMA table_info([{table}])")
            cols = [r[1] for r in cur.fetchall()]
            if "sura" not in cols or "aya" not in cols or "tafsir" not in cols:
                raise SystemExit(f"Unexpected schema for {table}: {cols}")

            out_dir = RAW / "tafsircenter" / tafsir_id
            out_dir.mkdir(parents=True, exist_ok=True)
            summary["extracted"][tafsir_id] = {}

            for surah, ayah in TARGET_AYAT:
                cur.execute(
                    f"SELECT [tafsir] FROM [{table}] WHERE [sura]=? AND [aya]=?",
                    (surah, ayah),
                )
                row = cur.fetchone()
                if not row or row[0] is None:
                    raise SystemExit(f"Missing {table} row for {surah}:{ayah}")
                text = row[0]
                if not isinstance(text, str):
                    text = str(text)

                key = f"{surah}_{ayah}"
                dest = out_dir / f"{key}.txt"
                rel = str(dest.relative_to(ROOT)).replace("\\", "/")
                data = text.encode("utf-8")
                digest = _sha256_bytes(data)
                source_url = f"sqlite:quran.db:{table}:{surah}:{ayah}"

                if dest.is_file():
                    existing = dest.read_bytes()
                    existing_sha = _sha256_bytes(existing)
                    if existing_sha == digest:
                        print(f"skip {rel} (sha256 match)")
                        entry = _entry_for_path(manifest, rel)
                        if entry is None:
                            manifest.setdefault("entries", []).append(
                                {
                                    "url": source_url,
                                    "path": rel,
                                    "timestamp_utc": _utc_now(),
                                    "http_status": None,
                                    "byte_length": len(data),
                                    "sha256": digest,
                                    "kind": "extracted_text",
                                }
                            )
                        summary["extracted"][tafsir_id][key] = {
                            "path": rel,
                            "char_length": len(text),
                            "sha256": digest,
                            "skipped": True,
                        }
                        continue
                    raise SystemExit(
                        f"File exists with different sha256: {rel}\n"
                        f"  on disk {existing_sha}\n  db     {digest}"
                    )

                dest.write_bytes(data)
                manifest.setdefault("entries", []).append(
                    {
                        "url": source_url,
                        "path": rel,
                        "timestamp_utc": _utc_now(),
                        "http_status": None,
                        "byte_length": len(data),
                        "sha256": digest,
                        "kind": "extracted_text",
                    }
                )
                summary["extracted"][tafsir_id][key] = {
                    "path": rel,
                    "char_length": len(text),
                    "sha256": digest,
                    "skipped": False,
                }
                print(f"wrote {rel} chars={len(text)} sha256={digest[:12]}")
    finally:
        conn.close()

    _save_manifest(manifest)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract multi-tafsir verse texts (read-only DB).")
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="Path to quran.db (opened read-only)",
    )
    args = parser.parse_args(argv)
    extract(args.db.resolve())


if __name__ == "__main__":
    main()
